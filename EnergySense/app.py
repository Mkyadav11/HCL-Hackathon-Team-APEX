import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

st.set_page_config(
    page_title="EnergySense",
    page_icon="⚡",
    layout="wide",
)


@st.cache_data
def read_csv_if_present(filename, **kwargs):
    path = DATA_DIR / filename
    if path.exists():
        return pd.read_csv(path, **kwargs)
    return pd.DataFrame()


@st.cache_data
def load_data():
    readings = pd.read_csv(
        DATA_DIR / "selected_buildings.csv",
        parse_dates=["timestamp"],
    )
    evaluation = pd.read_csv(DATA_DIR / "forecast_evaluation.csv")
    forecasts = pd.read_csv(
        DATA_DIR / "forecast_uncertainty.csv",
        parse_dates=["timestamp"],
    )
    anomalies = pd.read_csv(
        DATA_DIR / "energy_anomalies.csv",
        parse_dates=["timestamp"],
    )
    recommendations = pd.read_csv(DATA_DIR / "energy_recommendations.csv")

    # Person 2's Hog dataset outputs are loaded separately because their
    # building IDs differ from the Panther/Bull forecasting dataset.
    quality = read_csv_if_present("data_quality_report.csv")
    anomaly_summary = read_csv_if_present("anomaly_summary.csv")
    flatlines = read_csv_if_present("flatline_candidates.csv")
    event_path = DATA_DIR / "high_consumption_events.csv"
    events = pd.DataFrame()
    if event_path.exists():
        events = pd.read_csv(event_path)
    building_summary = read_csv_if_present("building_dashboard_summary.csv")
    monthly = read_csv_if_present("donnie_monthly_comparison.csv")

    return (
        readings, evaluation, forecasts, anomalies, recommendations,
        quality, anomaly_summary, flatlines, events, building_summary, monthly
    )


try:
    (
        readings, evaluation, forecasts, anomalies, recommendations,
        quality, anomaly_summary, flatlines, events, building_summary, monthly
    ) = load_data()
except Exception as error:
    st.error(f"Could not load project data: {error}")
    st.info("Check that the five original CSV files exist inside the data folder.")
    st.stop()


buildings = [c for c in readings.columns if c != "timestamp"]

st.title("⚡ EnergySense")
st.subheader("Energy Analytics Copilot")
st.caption(
    "Explore electricity use, forecasts, uncertainty, anomalies, "
    "data quality, and data-driven recommendations."
)

with st.sidebar:
    st.header("Dashboard Controls")
    selected_building = st.selectbox("Choose a forecast building", buildings)
    st.caption("Forecast dataset period")
    st.write(
        f"{readings['timestamp'].min():%Y-%m-%d} to "
        f"{readings['timestamp'].max():%Y-%m-%d}"
    )
    st.caption("Person 2's Hog dataset is shown separately in Data Quality & Insights.")

# Prepare data for the selected forecast building.
building_readings = readings[["timestamp", selected_building]].copy()
building_readings = building_readings.rename(
    columns={selected_building: "actual"}
)
valid_readings = building_readings.dropna(subset=["actual"])

if not valid_readings.empty:
    latest_row = valid_readings.iloc[-1]
    latest_value = float(latest_row["actual"])
    latest_timestamp = latest_row["timestamp"]
    average_value = float(valid_readings["actual"].mean())
else:
    latest_value = None
    latest_timestamp = None
    average_value = None

building_forecasts = forecasts[forecasts["building"] == selected_building].copy()
building_anomalies = anomalies[anomalies["building"] == selected_building].copy()
building_recommendations = recommendations[
    recommendations["building"] == selected_building
]
building_metrics = evaluation[evaluation["building"] == selected_building]

st.header("Building Overview")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Selected building", selected_building.replace("_", " "))
m2.metric(
    "Latest available reading",
    f"{latest_value:,.2f}" if latest_value is not None else "N/A",
)
m3.metric(
    "Historical average",
    f"{average_value:,.2f}" if average_value is not None else "N/A",
)
m4.metric("Potential anomalies", len(building_anomalies))

if latest_timestamp is not None:
    st.caption(f"Latest available reading timestamp: {latest_timestamp:%Y-%m-%d %H:%M}")
st.caption(
    "Readings use the dataset's original units. Historical averages use "
    "available non-missing readings."
)

# Rule-based Q&A over the forecasting dataset.
st.header("Ask EnergySense")
question = st.text_input(
    "Ask a question about your buildings",
    placeholder="Example: Which building has the highest WAPE?",
)

if st.button("Answer question"):
    q = question.lower().strip()
    if not q:
        st.warning("Enter a question first.")

    elif (
        "most anomalies" in q
        or "highest number of anomalies" in q
        or "building has the most anomaly" in q
    ):
        counts = anomalies.groupby("building").size()
        if counts.empty:
            st.info("No anomaly records are available.")
        else:
            top_building = counts.idxmax()
            st.write(
                f"**{top_building}** has the most potential anomalies: "
                f"**{int(counts.max())}**."
            )
            count_table = (
                counts.rename("anomaly_count")
                .sort_values(ascending=False)
                .rename_axis("building")
                .reset_index()
            )
            st.dataframe(count_table, width="stretch", hide_index=True)

    elif "highest wape" in q or "worst wape" in q:
        valid = evaluation.dropna(subset=["WAPE_percent"])
        if valid.empty:
            st.info("No WAPE values are available.")
        else:
            row = valid.loc[valid["WAPE_percent"].idxmax()]
            st.write(
                f"**{row['building']}** has the highest WAPE: "
                f"**{row['WAPE_percent']:.2f}%**."
            )

    elif "lowest wape" in q or "best wape" in q:
        valid = evaluation.dropna(subset=["WAPE_percent"])
        if valid.empty:
            st.info("No WAPE values are available.")
        else:
            row = valid.loc[valid["WAPE_percent"].idxmin()]
            st.write(
                f"**{row['building']}** has the lowest WAPE: "
                f"**{row['WAPE_percent']:.2f}%**."
            )

    elif (
        "largest consumption decrease" in q
        or "biggest decrease" in q
        or "largest decrease" in q
    ):
        data = recommendations.copy()
        data["change_percent"] = pd.to_numeric(data["change_percent"], errors="coerce")
        data = data.dropna(subset=["change_percent"])
        data = data[data["change_percent"] < 0]
        if data.empty:
            st.info("No consumption decreases are available.")
        else:
            row = data.loc[data["change_percent"].idxmin()]
            st.write(
                f"**{row['building']}** had the largest decrease: "
                f"**{abs(row['change_percent']):.2f}% below its baseline**."
            )
            st.caption("This is a measured consumption change, not verified savings.")

    elif "uncertainty coverage" in q or "interval coverage" in q:
        normalized_question = q.replace(" ", "_")
        matched = [
            b for b in buildings
            if b.lower() in normalized_question or b.lower().replace("_", " ") in q
        ]
        if not matched:
            st.warning(
                "Include a building name, for example: What is the uncertainty "
                "coverage for Panther_education_Annetta?"
            )
        else:
            target = matched[0]
            data = evaluation[evaluation["building"] == target]
            if data.empty:
                st.info("No evaluation metrics were found for that building.")
            else:
                row = data.iloc[0]
                st.write(
                    f"Observed interval coverage for **{target}**: "
                    f"**{row['interval_coverage_percent']:.2f}%**."
                )
                st.caption(
                    "This is test-period coverage. It does not guarantee "
                    "90% coverage on future readings."
                )

    elif "high-severity" in q or "high severity" in q:
        high = anomalies[anomalies["severity"] == "High"]
        normalized_question = q.replace(" ", "_")
        matched = [
            b for b in buildings
            if b.lower() in normalized_question or b.lower().replace("_", " ") in q
        ]
        if matched:
            high = high[high["building"] == matched[0]]
        st.write(f"Found **{len(high)}** high-severity alerts.")
        st.dataframe(high, width="stretch", hide_index=True)

    elif "anomal" in q or "unusual reading" in q:
        counts = anomalies.groupby("building").size().sort_values(ascending=False)
        if counts.empty:
            st.info("No potential anomalies were flagged.")
        else:
            count_table = (
                counts.rename("anomaly_count")
                .rename_axis("building")
                .reset_index()
            )
            st.write("Potential anomaly counts by building:")
            st.dataframe(count_table, width="stretch", hide_index=True)

    elif "increase" in q:
        data = recommendations.copy()
        data["change_percent"] = pd.to_numeric(data["change_percent"], errors="coerce")
        data = data.dropna(subset=["change_percent"])
        data = data[data["change_percent"] > 0].sort_values(
            "change_percent", ascending=False
        )
        if data.empty:
            st.write("No buildings had an increase versus their baseline.")
        else:
            st.dataframe(data, width="stretch", hide_index=True)

    elif "decrease" in q:
        data = recommendations.copy()
        data["change_percent"] = pd.to_numeric(data["change_percent"], errors="coerce")
        data = data.dropna(subset=["change_percent"])
        data = data[data["change_percent"] < 0].sort_values("change_percent")
        if data.empty:
            st.write("No buildings had a consumption decrease.")
        else:
            row = data.iloc[0]
            st.write(
                f"**{row['building']}** had the largest decrease: "
                f"**{abs(row['change_percent']):.2f}%**."
            )
            st.dataframe(data, width="stretch", hide_index=True)

    elif (
        "forecast" in q or "mae" in q or "rmse" in q or "accuracy" in q
    ):
        normalized_question = q.replace(" ", "_")
        matched = [
            b for b in buildings
            if b.lower() in normalized_question or b.lower().replace("_", " ") in q
        ]
        data = evaluation.copy()
        if matched:
            data = data[data["building"] == matched[0]]
        st.dataframe(data, width="stretch", hide_index=True)

    else:
        st.info(
            "I couldn't match that question yet. Try highest or lowest WAPE, "
            "most anomalies, uncertainty coverage, forecast metrics, or "
            "consumption increases and decreases."
        )

st.caption(
    "Q&A currently uses predefined question patterns over local CSV files. "
    "It is not yet an LLM-powered natural-language-to-SQL system."
)

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "Usage & Forecast",
        "Forecast Evaluation",
        "Anomaly Alerts",
        "Recommendations",
        "Data Quality & Insights",
    ]
)

with tab1:
    st.header("Electricity Usage and Forecast")
    view = st.radio(
        "View",
        ["Recent 30 days", "Full history"],
        horizontal=True,
    )
    if view == "Recent 30 days":
        start = building_readings["timestamp"].max() - pd.Timedelta(days=30)
        chart_data = building_readings[building_readings["timestamp"] >= start]
        forecast_data = building_forecasts[building_forecasts["timestamp"] >= start]
    else:
        chart_data = building_readings
        forecast_data = building_forecasts

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=chart_data["timestamp"],
            y=chart_data["actual"],
            mode="lines",
            name="Actual electricity",
        )
    )
    if not forecast_data.empty:
        forecast_data = forecast_data.sort_values("timestamp")
        fig.add_trace(
            go.Scatter(
                x=forecast_data["timestamp"],
                y=forecast_data["upper_90_estimate"],
                mode="lines",
                line=dict(width=0),
                showlegend=False,
                name="Upper estimate",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=forecast_data["timestamp"],
                y=forecast_data["lower_90_estimate"],
                mode="lines",
                line=dict(width=0),
                fill="tonexty",
                fillcolor="rgba(100,149,237,0.20)",
                name="Estimated range",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=forecast_data["timestamp"],
                y=forecast_data["predicted"],
                mode="lines",
                name="Forecast",
                line=dict(dash="dash"),
            )
        )
    fig.update_layout(
        xaxis_title="Timestamp",
        yaxis_title="Electricity reading (dataset units)",
        hovermode="x unified",
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "The shaded region is an empirical error-based range, not a guaranteed "
        "90% prediction interval."
    )

with tab2:
    st.header("Forecast Performance")
    if building_metrics.empty:
        st.warning("No evaluation metrics found for this building.")
    else:
        row = building_metrics.iloc[0]
        a, b, c = st.columns(3)
        a.metric("MAE", f"{row['MAE']:.3f}")
        b.metric("RMSE", f"{row['RMSE']:.3f}")
        c.metric("WAPE", f"{row['WAPE_percent']:.2f}%")
        st.write(f"Valid test hours: {int(row['valid_test_hours'])}")
        if "interval_coverage_percent" in row.index:
            st.metric(
                "Estimated range coverage",
                f"{row['interval_coverage_percent']:.2f}%",
            )
        st.caption(
            "MAE and RMSE measure prediction error. WAPE expresses total "
            "absolute error relative to total absolute actual readings. "
            "Lower values generally indicate better forecasts."
        )

with tab3:
    st.header("Potential Anomaly Alerts")
    if building_anomalies.empty:
        st.success("No potential anomalies were flagged for this building.")
    else:
        high_count = (building_anomalies["severity"] == "High").sum()
        moderate_count = (building_anomalies["severity"] == "Moderate").sum()
        a, b, c = st.columns(3)
        a.metric("Total alerts", len(building_anomalies))
        b.metric("High", int(high_count))
        c.metric("Moderate", int(moderate_count))
        severity_filter = st.multiselect(
            "Filter by severity",
            ["High", "Moderate"],
            default=["High", "Moderate"],
        )
        filtered = building_anomalies[
            building_anomalies["severity"].isin(severity_filter)
        ].sort_values("timestamp", ascending=False)
        st.dataframe(filtered, width="stretch", hide_index=True)
        st.download_button(
            "Download building alerts",
            data=filtered.to_csv(index=False).encode("utf-8"),
            file_name="building_anomalies.csv",
            mime="text/csv",
        )
        st.warning(
            "Alerts require investigation. They do not prove energy waste "
            "or equipment failure."
        )

with tab4:
    st.header("Energy-Saving Recommendations")
    if building_recommendations.empty:
        st.info("No recommendation record found for this building.")
    else:
        recommendation = building_recommendations.iloc[0]
        change = recommendation["change_percent"]
        st.subheader(str(recommendation["status"]))
        if pd.notna(change):
            st.metric("Change versus weekly baseline", f"{change:+.2f}%")
        left, right = st.columns(2)
        left.write("**Recent weekly total**")
        left.write(recommendation["recent_week_total"])
        right.write("**Baseline weekly median**")
        right.write(recommendation["baseline_weekly_median"])
        st.markdown("### Suggested next action")
        st.write(recommendation["recommendation"])
        st.caption(
            "Recommendations are prompts for investigation, not verified "
            "energy savings. Occupancy, weather, and schedules can affect use."
        )

with tab5:
    st.header("Data Quality & Insights")
    st.info(
        "This tab presents Person 2's separate Hog-building dataset. "
        "Its building IDs are different from the Panther/Bull forecast dataset; "
        "the datasets are not joined together."
    )

    if not quality.empty:
        st.subheader("Data Quality Report")
        q = quality.copy()
        for col in ["total_rows", "valid_readings", "missing_readings",
                    "negative_readings", "unique_timestamps", "completeness_pct"]:
            if col in q.columns:
                q[col] = pd.to_numeric(q[col], errors="coerce")
        q1, q2, q3 = st.columns(3)
        q1.metric("Buildings checked", q["building_id"].nunique() if "building_id" in q else len(q))
        q2.metric(
            "Average completeness",
            f"{q['completeness_pct'].mean():.2f}%"
            if "completeness_pct" in q else "N/A",
        )
        q3.metric(
            "Missing readings",
            f"{int(q['missing_readings'].fillna(0).sum()):,}"
            if "missing_readings" in q else "N/A",
        )
        st.dataframe(q, width="stretch", hide_index=True)
        st.download_button(
            "Download data quality report",
            q.to_csv(index=False).encode("utf-8"),
            "data_quality_report.csv",
            "text/csv",
        )
    else:
        st.warning("data_quality_report.csv was not found.")

    if not building_summary.empty:
        st.subheader("Building-Level Summary")
        bs = building_summary.copy()
        if "anomaly_count" in bs.columns:
            bs["anomaly_count"] = pd.to_numeric(bs["anomaly_count"], errors="coerce")
        if "average_reading" in bs.columns:
            bs["average_reading"] = pd.to_numeric(bs["average_reading"], errors="coerce")
        if "peak_reading" in bs.columns:
            bs["peak_reading"] = pd.to_numeric(bs["peak_reading"], errors="coerce")
        if "anomaly_count" in bs.columns and not bs.empty:
            top = bs.sort_values("anomaly_count", ascending=False).iloc[0]
            st.metric(
                "Most flagged Hog building",
                str(top.get("building_id", "N/A")),
                f"{int(top['anomaly_count']):,} candidate events",
            )
        st.dataframe(bs, width="stretch", hide_index=True)
        st.download_button(
            "Download building summary",
            bs.to_csv(index=False).encode("utf-8"),
            "building_dashboard_summary.csv",
            "text/csv",
        )

    if not anomaly_summary.empty:
        st.subheader("Anomaly Summary")
        st.dataframe(anomaly_summary, width="stretch", hide_index=True)
        if "event_count" in anomaly_summary.columns:
            chart = anomaly_summary.copy()
            chart["event_count"] = pd.to_numeric(chart["event_count"], errors="coerce")
            chart["category"] = (
                chart.get("anomaly_type", pd.Series(index=chart.index, dtype=str)).astype(str)
                + " — "
                + chart.get("severity", pd.Series(index=chart.index, dtype=str)).astype(str)
            )
            st.bar_chart(chart.set_index("category")["event_count"])
        st.download_button(
            "Download anomaly summary",
            anomaly_summary.to_csv(index=False).encode("utf-8"),
            "anomaly_summary.csv",
            "text/csv",
        )

    if not monthly.empty:
        st.subheader("Seasonal Trend: Hog_education_Donnie")
        m = monthly.copy()
        m["year"] = pd.to_numeric(m["year"], errors="coerce")
        m["month"] = pd.to_numeric(m["month"], errors="coerce")
        m["average_consumption"] = pd.to_numeric(
            m["average_consumption"], errors="coerce"
        )
        m = m.dropna(subset=["year", "month", "average_consumption"])
        m["month_name"] = m["month"].astype(int).map(
            {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
             7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}
        )
        fig_month = go.Figure()
        for year in sorted(m["year"].unique()):
            year_data = m[m["year"] == year].sort_values("month")
            fig_month.add_trace(
                go.Scatter(
                    x=year_data["month_name"],
                    y=year_data["average_consumption"],
                    mode="lines+markers",
                    name=str(int(year)),
                )
            )
        fig_month.update_layout(
            xaxis_title="Month",
            yaxis_title="Average reading (dataset units)",
            hovermode="x unified",
        )
        st.plotly_chart(fig_month, width="stretch")
        st.caption(
            "Person 2 observed higher monthly averages from May through September "
            "in both years. This may reflect seasonality and should be considered "
            "when reviewing anomaly alerts."
        )
        st.download_button(
            "Download Donnie monthly comparison",
            monthly.to_csv(index=False).encode("utf-8"),
            "donnie_monthly_comparison.csv",
            "text/csv",
        )

    if not flatlines.empty:
        st.subheader("Flatline Candidates")
        st.caption(
            "These are readings that remained unchanged for an extended period "
            "and should be reviewed; they are not automatically confirmed meter faults."
        )
        st.dataframe(flatlines, width="stretch", hide_index=True)
        st.download_button(
            "Download flatline candidates",
            flatlines.to_csv(index=False).encode("utf-8"),
            "flatline_candidates.csv",
            "text/csv",
        )

    if not events.empty:
        st.subheader("High-Consumption Events")
        st.caption(
            f"{len(events):,} candidate event rows are available. Filter before "
            "reviewing or downloading. The 30% threshold is exploratory and "
            "events are not confirmed faults."
        )
        filtered_events = events.copy()
        if "building_id" in filtered_events.columns:
            event_buildings = sorted(filtered_events["building_id"].dropna().unique())
            chosen_building = st.selectbox(
                "Filter Hog building",
                ["All buildings"] + event_buildings,
                key="hog_event_building",
            )
            if chosen_building != "All buildings":
                filtered_events = filtered_events[
                    filtered_events["building_id"] == chosen_building
                ]
        if "severity" in filtered_events.columns:
            severities = sorted(filtered_events["severity"].dropna().unique())
            chosen_severity = st.multiselect(
                "Filter event severity",
                severities,
                default=severities,
                key="hog_event_severity",
            )
            filtered_events = filtered_events[
                filtered_events["severity"].isin(chosen_severity)
            ]
        st.write(f"Showing **{len(filtered_events):,}** matching events.")
        st.dataframe(
            filtered_events.head(1000),
            width="stretch",
            hide_index=True,
        )
        if len(filtered_events) > 1000:
            st.caption("Showing the first 1,000 matching rows for display performance.")
        st.download_button(
            "Download filtered high-consumption events",
            filtered_events.to_csv(index=False).encode("utf-8"),
            "filtered_high_consumption_events.csv",
            "text/csv",
        )
    else:
        st.warning("high_consumption_events.csv was not found.")

st.divider()
st.caption(
    "EnergySense | Hackathon prototype | Forecasts and alerts support "
    "investigation, not automatic decisions."
)
