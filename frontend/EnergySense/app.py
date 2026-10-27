"""
EnergySense — AI-Powered Building Energy Analytics Copilot
Frontend Application (Streamlit + Plotly)
Team APEX: Integrated Application combining Persons 1, 2, 3, and 4.
"""

import os
import sys
from pathlib import Path

# Ensure project root and frontend directory are in sys.path
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Any, Dict, List

# Local module imports
from api_client import (
    check_backend_health,
    query_copilot,
    get_building_summaries,
    get_recent_anomalies,
    get_quick_forecast,
    DEFAULT_BACKEND_URL
)
from charts import (
    build_chart_from_spec,
    build_campus_overview_bar,
    build_anomaly_breakdown_pie
)

# -----------------------------------------
# 1. Page Configuration & Styling
# -----------------------------------------
st.set_page_config(
    page_title="EnergySense — Energy Analytics Copilot",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------
# 2. Sidebar Configuration & System Health
# -----------------------------------------
with st.sidebar:
    st.title("⚡ EnergySense")
    st.caption("AI-Powered Campus Energy Copilot | Team APEX")
    st.divider()

    st.subheader("⚙️ Backend Connection")
    backend_url = st.text_input(
        "Backend API URL",
        value=os.environ.get("BACKEND_URL", DEFAULT_BACKEND_URL),
        help="FastAPI orchestrator URL (default: http://localhost:8000)"
    )

    is_healthy = check_backend_health(backend_url)
    if is_healthy:
        st.success("🟢 FastAPI Backend Online")
    else:
        st.warning("🟡 Direct In-Process Mode (FastAPI offline)")
        st.caption("Using backend service direct engine fallback.")

    st.divider()
    st.subheader("🏛️ Campus Specifications")
    st.markdown("""
    - **Monitored Buildings:** 15 Campus Facilities
    - **Historical Readings:** 263,160 Hourly Intervals
    - **Anomaly Events:** 41,499 Identified Records
    - **Interval Granularity:** Hourly (2016–2017)
    - **Primary Metric:** Electricity Consumption (kWh)
    """)

    st.divider()
    st.subheader("👥 Team APEX Architecture")
    st.markdown("""
    - **Person 1:** AI Orchestration, NL-to-SQL, AST Safety
    - **Person 2:** Canonical Schema, Data Quality, Anomalies
    - **Person 3:** Forecasting, Uncertainty, Recommendations
    - **Person 4:** Streamlit UI & Interactive Plotly Charts
    """)

# -----------------------------------------
# 3. Main Dashboard Header & Campus KPIs
# -----------------------------------------
st.title("⚡ EnergySense Copilot")
st.markdown("### Autonomous Campus Energy Intelligence & Decision Support")

# Summary KPI cards using real system stats
col1, col2, col3, col4 = st.columns(4)
col1.metric("Buildings Monitored", "15 Buildings", "Site 'Hog'")
col2.metric("Total Ingested Readings", "263,160", "100% Quality Grid")
col3.metric("Flagged Anomalies", "41,499", "41,497 Spikes + 2 Freezes")
col4.metric("Forecast Confidence", "90% Empirical", "Calibrated Bounds")

st.divider()

# -----------------------------------------
# 4. Multi-Tab Navigation
# -----------------------------------------
tab_copilot, tab_buildings, tab_anomalies, tab_forecast, tab_recommendations = st.tabs([
    "💬 Ask AI Copilot",
    "📊 Campus Buildings",
    "🚨 Anomaly Detection",
    "🔮 Energy Forecasting",
    "💡 Savings Recommendations"
])

# =========================================
# TAB 1: ASK AI COPILOT
# =========================================
with tab_copilot:
    st.header("💬 Natural Language Energy Assistant")
    st.write(
        "Ask any question about historical energy consumption, anomalous spikes, "
        "future forecasts, or efficiency recommendations."
    )

    # Quick example prompts
    st.markdown("**Suggested Questions:**")
    example_cols = st.columns(3)
    
    prompt_p1 = "Which building consumed the most electricity last week?"
    prompt_p2 = "Which buildings have unusually high electricity consumption at night?"
    prompt_p3 = "Has a meter stopped reporting?"
    prompt_p4 = "Forecast electricity consumption for Donnie Education Hall over the next 24 hours"
    prompt_p5 = "Show me the expected consumption for the next seven days"
    prompt_p6 = "What actions could help reduce energy wastage?"

    with example_cols[0]:
        if st.button("🏢 Top Consumer Last Week", use_container_width=True):
            st.session_state["copilot_query"] = prompt_p1
        if st.button("🔮 24-Hour Forecast Donnie", use_container_width=True):
            st.session_state["copilot_query"] = prompt_p4

    with example_cols[1]:
        if st.button("🚨 Night-Time Spikes", use_container_width=True):
            st.session_state["copilot_query"] = prompt_p2
        if st.button("📈 7-Day Forecast", use_container_width=True):
            st.session_state["copilot_query"] = prompt_p5

    with example_cols[2]:
        if st.button("⚠️ Meter Flatlines / Freezes", use_container_width=True):
            st.session_state["copilot_query"] = prompt_p3
        if st.button("💡 Energy-Saving Actions", use_container_width=True):
            st.session_state["copilot_query"] = prompt_p6

    # Input Form
    current_val = st.session_state.get("copilot_query", "")
    with st.form("copilot_form"):
        user_question = st.text_input(
            "Enter your energy query:",
            value=current_val,
            placeholder="e.g. Which building consumed the most electricity last week?"
        )
        submit_btn = st.form_submit_button("🚀 Run Analysis", type="primary")

    if submit_btn and user_question.strip():
        with st.spinner("Analyzing question with AI Copilot..."):
            res = query_copilot(user_question.strip(), base_url=backend_url)

        st.session_state["last_response"] = res
        st.session_state["last_question"] = user_question.strip()

    # Render Copilot Results
    if "last_response" in st.session_state:
        response = st.session_state["last_response"]
        st.subheader("💡 Copilot Response")

        # Clarification prompt handling
        if response.get("needs_clarification"):
            st.warning(f"🤔 **Clarification Needed:** {response.get('clarification_question')}")
            st.info(
                "Your question is ambiguous. Please specify a measurable metric such as "
                "'highest total kWh', 'night-time spike anomalies', or 'highest baseline deviation'."
            )
        else:
            # Main answer
            st.markdown(f"**{response.get('answer', '')}**")

            # Chart rendering
            chart_spec = response.get("chart")
            data_rows = response.get("data", [])
            if chart_spec and data_rows:
                chart_fig = build_chart_from_spec(chart_spec, data_rows)
                if chart_fig:
                    st.plotly_chart(chart_fig, use_container_width=True)

            # Data Table
            if data_rows:
                with st.expander("📋 View Underlying Data Records", expanded=False):
                    df_res = pd.DataFrame(data_rows)
                    st.dataframe(df_res, use_container_width=True)
                    csv = df_res.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        "📥 Download CSV",
                        data=csv,
                        file_name="copilot_results.csv",
                        mime="text/csv"
                    )

            # Sanitized SQL Query Details
            if response.get("sql_query"):
                with st.expander("🔒 Validated AST SQL Query (Read-Only)", expanded=False):
                    st.code(response["sql_query"], language="sql")
                    st.caption("Verified by SQLGlot AST Validator against authorized tables & row limits.")

            # Caveats / Disclaimers
            if response.get("warnings"):
                for w in response["warnings"]:
                    st.caption(f"ℹ️ *Note: {w}*")

            # Execution details
            exec_time = response.get("execution_time_ms", 0.0)
            intent = response.get("intent", "unknown")
            st.caption(f"Execution time: {exec_time:.1f}ms | Intent: `{intent}` | Status: `{response.get('status')}`")


# =========================================
# TAB 2: CAMPUS BUILDINGS & CONSUMPTION
# =========================================
with tab_buildings:
    st.header("📊 Campus Building Energy Consumption")
    st.write("Real electricity consumption metrics across all 15 monitored facilities.")

    buildings_summary = get_building_summaries(base_url=backend_url)
    if buildings_summary:
        df_b = pd.DataFrame(buildings_summary)
        
        # Overview Bar Chart
        fig_b = build_campus_overview_bar(buildings_summary)
        st.plotly_chart(fig_b, use_container_width=True)

        st.subheader("📋 Building Profile & Summary Statistics")
        st.dataframe(
            df_b[[
                "building_id", "name", "primary_use", "reading_count",
                "average_reading", "peak_reading", "anomaly_count"
            ]].rename(columns={
                "building_id": "Building ID",
                "name": "Building Name",
                "primary_use": "Primary Use",
                "reading_count": "Total Readings",
                "average_reading": "Average Hourly kWh",
                "peak_reading": "Peak Hourly kWh",
                "anomaly_count": "Anomaly Count"
            }),
            use_container_width=True
        )
    else:
        st.info("Loading building data...")


# =========================================
# TAB 3: ANOMALY DETECTION & HEALTH
# =========================================
with tab_anomalies:
    st.header("🚨 Anomaly Detection & Meter Health")
    st.write(
        "Identified consumption anomalies and meter telemetry freezes from the "
        "canonical 41,499 event dataset."
    )

    anomalies_list = get_recent_anomalies(limit=500, base_url=backend_url)

    if anomalies_list:
        a_col1, a_col2 = st.columns([1, 2])

        with a_col1:
            pie_fig = build_anomaly_breakdown_pie(anomalies_list)
            st.plotly_chart(pie_fig, use_container_width=True)

        with a_col2:
            st.subheader("🔍 Filter Detected Anomalies")
            df_a = pd.DataFrame(anomalies_list)
            severities = ["All"] + sorted(list(df_a["severity"].unique()))
            selected_sev = st.selectbox("Filter by Severity:", severities)

            if selected_sev != "All":
                filtered_df = df_a[df_a["severity"] == selected_sev]
            else:
                filtered_df = df_a

            st.dataframe(
                filtered_df[[
                    "detected_at", "building_name", "anomaly_type",
                    "actual_value", "baseline_value", "deviation_pct", "severity"
                ]].head(50),
                use_container_width=True
            )

        st.subheader("🧊 Telemetry Freezes / Flatlines (Memorial Day Freeze)")
        st.markdown("""
        - **Hog_assembly_Colette** & **Hog_education_Dona**: Experienced a **125-hour telemetry freeze**
          between `2017-05-27` and `2017-06-01` where meter readings remained completely static.
        - **Status:** Verified telemetry disruption (zero consumption fluctuation during holiday weekend).
        """)
    else:
        st.info("No anomaly records loaded.")


# =========================================
# TAB 4: ENERGY FORECASTING & UNCERTAINTY
# =========================================
with tab_forecast:
    st.header("🔮 Hourly Energy Demand Forecasting")
    st.write(
        "Time-series predictions powered by Person 3's seasonal persistence model "
        "with calibrated 90% empirical error intervals."
    )

    f_col1, f_col2 = st.columns([2, 1])
    with f_col1:
        building_options = [
            "Hog_education_Donnie", "Hog_education_Casandra", "Hog_education_Dona",
            "Hog_education_Rosanne", "Hog_office_Amelia", "Hog_assembly_Colette",
            "Hog_assembly_Myles", "Hog_lodging_Hattie"
        ]
        chosen_building = st.selectbox("Select Building:", building_options)

    with f_col2:
        horizon_opt = st.selectbox("Forecast Horizon:", [24, 48, 168], format_func=lambda x: f"{x} Hours ({x//24} Days)")

    if st.button("Generate Forecast", type="primary"):
        with st.spinner("Computing forecast and uncertainty intervals..."):
            forecast_res = get_quick_forecast([chosen_building], horizon_hours=horizon_opt)

        if forecast_res.get("status") == "success" and forecast_res.get("data"):
            f_data = forecast_res["data"]
            df_f = pd.DataFrame(f_data)

            # Render Forecast Plot with Confidence Band
            chart_spec = {
                "type": "line",
                "x": "timestamp",
                "y": "forecast_kwh",
                "x_label": "Future Timestamp",
                "y_label": "Forecast Electricity (kWh)",
                "title": f"{chosen_building} — {horizon_opt}-Hour Demand Forecast"
            }
            fig_fc = build_chart_from_spec(chart_spec, f_data)
            st.plotly_chart(fig_fc, use_container_width=True)

            # Key Forecast Summary Metrics
            total_kwh = df_f["forecast_kwh"].sum()
            min_kwh = df_f["forecast_kwh"].min()
            max_kwh = df_f["forecast_kwh"].max()
            margin = df_f["uncertainty_margin_kwh"].mean()

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Expected Energy", f"{total_kwh:,.1f} kWh")
            m2.metric("Peak Hourly Demand", f"{max_kwh:,.1f} kWh")
            m3.metric("Minimum Expected Load", f"{min_kwh:,.1f} kWh")
            m4.metric("90% Margin of Error", f"±{margin:,.1f} kWh")

            with st.expander("View Forecast Data Points"):
                st.dataframe(df_f, use_container_width=True)
        else:
            st.error("Failed to generate forecast for the selected building.")


# =========================================
# TAB 5: SAVINGS RECOMMENDATIONS
# =========================================
with tab_recommendations:
    st.header("💡 Evidence-Based Energy Savings Recommendations")
    st.write(
        "Identifies facilities with >15% above-baseline consumption and produces "
        "tailored operational conservation actions."
    )

    try:
        from backend.app.services.forecast_service import generate_recommendations
        rec_data = generate_recommendations()

        if rec_data.get("status") == "success":
            total_sav = rec_data.get("total_potential_weekend_savings_kwh", 0)
            st.success(f"💰 **Total Potential Weekend Savings:** {total_sav:,.1f} kWh across campus")

            recs = rec_data.get("recommendations", [])
            df_rec = pd.DataFrame(recs)

            st.dataframe(
                df_rec[[
                    "building", "primary_use", "average_hourly_kwh", "peak_hourly_kwh",
                    "status", "potential_weekend_savings_kwh", "recommendation"
                ]].rename(columns={
                    "building": "Facility Name",
                    "primary_use": "Primary Use",
                    "average_hourly_kwh": "Average kWh",
                    "peak_hourly_kwh": "Peak kWh",
                    "status": "Operational Status",
                    "potential_weekend_savings_kwh": "Weekend Savings (kWh)",
                    "recommendation": "Recommended Engineering Action"
                }),
                use_container_width=True
            )
        else:
            st.error("Could not load recommendations.")
    except Exception as err:
        st.error(f"Error loading recommendations: {str(err)}")

# -----------------------------------------
# 5. Footer
# -----------------------------------------
st.divider()
st.caption(
    "EnergySense Copilot | Team APEX | Fully Integrated Backend & Frontend "
    "(Persons 1, 2, 3, and 4)"
)
