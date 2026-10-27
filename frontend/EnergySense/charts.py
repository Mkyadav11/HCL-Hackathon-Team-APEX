"""
EnergySense Visualization Engine
Translates backend ChartSpec and raw analytics data into interactive Plotly figures.
Supports shaded uncertainty ribbons (90% confidence), anomaly severities, and consumption bars.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Any, Dict, List, Optional


def build_chart_from_spec(
    chart_spec: Optional[Dict[str, Any]],
    data: List[Dict[str, Any]],
    title_override: Optional[str] = None
) -> Optional[go.Figure]:
    """
    Construct a Plotly figure from backend ChartSpec and data rows.
    
    Expected ChartSpec fields:
        type: "line" | "bar"
        x: str (column name for X axis)
        y: str (column name for Y axis)
        x_label: str
        y_label: str
        title: str
    """
    if not chart_spec or not data:
        return None

    df = pd.DataFrame(data)
    if df.empty:
        return None

    chart_type = chart_spec.get("type", "bar")
    x_col = chart_spec.get("x")
    y_col = chart_spec.get("y")
    x_label = chart_spec.get("x_label", x_col)
    y_label = chart_spec.get("y_label", y_col)
    title = title_override or chart_spec.get("title", "Energy Analytics")

    # Ensure specified columns exist, or pick fallback
    if x_col not in df.columns:
        x_col = df.columns[0]
    if y_col not in df.columns:
        numeric_cols = df.select_dtypes(include=["number"]).columns
        y_col = numeric_cols[0] if len(numeric_cols) > 0 else df.columns[-1]

    if chart_type == "line":
        fig = go.Figure()

        # Check for Person 3 calibrated uncertainty bounds
        has_bounds = (
            ("lower_bound_kwh" in df.columns and "upper_bound_kwh" in df.columns) or
            ("lower_bound" in df.columns and "upper_bound" in df.columns)
        )
        lower_col = "lower_bound_kwh" if "lower_bound_kwh" in df.columns else "lower_bound"
        upper_col = "upper_bound_kwh" if "upper_bound_kwh" in df.columns else "upper_bound"

        if has_bounds:
            # Upper bound line (invisible border for ribbon fill)
            fig.add_trace(go.Scatter(
                x=df[x_col],
                y=df[upper_col],
                mode="lines",
                line=dict(width=0),
                showlegend=False,
                name="Upper Bound (90%)",
                hoverinfo="skip"
            ))

            # Lower bound line with filled region up to upper bound
            fig.add_trace(go.Scatter(
                x=df[x_col],
                y=df[lower_col],
                mode="lines",
                line=dict(width=0),
                fill="tonexty",
                fillcolor="rgba(31, 119, 180, 0.20)",
                name="90% Confidence Interval",
                hovertemplate="Lower: %{y:.1f} kWh<extra></extra>"
            ))

        # Main prediction or actual consumption line
        fig.add_trace(go.Scatter(
            x=df[x_col],
            y=df[y_col],
            mode="lines+markers",
            name=y_label or "Electricity (kWh)",
            line=dict(color="#1f77b4", width=3),
            marker=dict(size=6, color="#1f77b4"),
            hovertemplate="<b>%{x}</b><br>Value: %{y:.1f} kWh<extra></extra>"
        ))

        fig.update_layout(
            title=dict(text=title, font=dict(size=16, color="#111827")),
            xaxis=dict(title=x_label, showgrid=True, gridcolor="#f3f4f6"),
            yaxis=dict(title=y_label, showgrid=True, gridcolor="#f3f4f6"),
            hovermode="x unified",
            template="plotly_white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=40, r=40, t=60, b=40)
        )
        return fig

    elif chart_type == "bar":
        # Sort descending if ranking
        if pd.api.types.is_numeric_dtype(df[y_col]):
            df_sorted = df.sort_values(by=y_col, ascending=False)
        else:
            df_sorted = df

        fig = px.bar(
            df_sorted,
            x=x_col,
            y=y_col,
            color=y_col if pd.api.types.is_numeric_dtype(df_sorted[y_col]) else None,
            color_continuous_scale="Blues",
            title=title,
            labels={x_col: x_label, y_col: y_label}
        )

        fig.update_layout(
            xaxis_tickangle=-45,
            template="plotly_white",
            coloraxis_showscale=False,
            margin=dict(l=40, r=40, t=60, b=80),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="#f3f4f6")
        )
        return fig

    return None


def build_campus_overview_bar(buildings: List[Dict[str, Any]]) -> go.Figure:
    """Build building electricity consumption bar chart from real database summaries."""
    if not buildings:
        return go.Figure()

    df = pd.DataFrame(buildings)
    name_col = "name" if "name" in df.columns else ("building_name" if "building_name" in df.columns else "building_id")
    val_col = "total_consumption_kwh" if "total_consumption_kwh" in df.columns else "avg_consumption_kwh"

    if val_col not in df.columns:
        numeric_cols = df.select_dtypes(include=["number"]).columns
        val_col = numeric_cols[0] if len(numeric_cols) > 0 else df.columns[1]

    df_sorted = df.sort_values(by=val_col, ascending=False)

    fig = px.bar(
        df_sorted,
        x=name_col,
        y=val_col,
        color=val_col,
        color_continuous_scale="Viridis",
        title="Actual Total Consumption Across Monitored Campus Buildings (kWh)",
        labels={name_col: "Building", val_col: "Total Consumption (kWh)"}
    )

    fig.update_layout(
        xaxis_tickangle=-40,
        template="plotly_white",
        coloraxis_showscale=False,
        margin=dict(l=30, r=30, t=50, b=90)
    )
    return fig


def build_anomaly_breakdown_pie(anomalies: List[Dict[str, Any]]) -> go.Figure:
    """Build pie breakdown of detected anomalies by severity."""
    if not anomalies:
        return go.Figure()

    df = pd.DataFrame(anomalies)
    sev_col = "severity" if "severity" in df.columns else "anomaly_type"
    if sev_col not in df.columns:
        return go.Figure()

    counts = df[sev_col].value_counts().reset_index()
    counts.columns = [sev_col, "count"]

    color_map = {
        "Critical": "#ef4444",
        "High": "#f97316",
        "Medium": "#eab308",
        "Low": "#3b82f6",
        "Info": "#6b7280"
    }

    fig = px.pie(
        counts,
        names=sev_col,
        values="count",
        color=sev_col,
        color_discrete_map=color_map,
        title="Detected Anomalies by Severity Level",
        hole=0.4
    )
    fig.update_layout(template="plotly_white", margin=dict(l=20, r=20, t=50, b=20))
    return fig
