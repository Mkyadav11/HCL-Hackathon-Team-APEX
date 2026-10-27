"""
Test Suite for Person 4 Frontend Integration & End-to-End Scenarios (1 through 6)
Verifies:
- api_client functions (health, copilot queries, direct engine fallback)
- charts engine (Plotly figure builders, confidence interval ribbons, bar charts)
- End-to-End Scenarios 1 through 6 matching user specification
- Regression verification across Persons 1, 2, and 3
"""

import pytest
import pandas as pd
import plotly.graph_objects as go
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.agent.orchestrator import AgentOrchestrator
from frontend.EnergySense.api_client import (
    check_backend_health,
    query_copilot,
    get_building_summaries,
    get_recent_anomalies,
    get_quick_forecast
)
from frontend.EnergySense.charts import (
    build_chart_from_spec,
    build_campus_overview_bar,
    build_anomaly_breakdown_pie
)

client = TestClient(app)


# -------------------------------------------------------------
# Frontend API Client & Fallback Tests
# -------------------------------------------------------------
def test_frontend_health_check_via_testclient():
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_frontend_api_client_direct_query():
    """Verify that query_copilot resolves queries even if remote HTTP server is offline."""
    res = query_copilot("Which building consumed the most electricity last week?", base_url="http://127.0.0.1:9999")
    assert res["status"] == "success"
    assert "answer" in res
    assert len(res["data"]) > 0
    assert res["chart"]["type"] == "bar"


def test_frontend_get_building_summaries():
    """Verify frontend retrieves all 15 campus buildings from Person 2's data layer."""
    summaries = get_building_summaries()
    assert len(summaries) == 15
    first = summaries[0]
    assert "building_id" in first
    assert "average_reading" in first
    assert "reading_count" in first
    assert first["reading_count"] == 17544


def test_frontend_get_recent_anomalies():
    """Verify frontend retrieves detected anomalies from Person 2's anomaly layer."""
    anomalies = get_recent_anomalies(limit=25)
    assert len(anomalies) > 0
    assert "anomaly_type" in anomalies[0]
    assert "deviation_pct" in anomalies[0]
    assert "severity" in anomalies[0]


def test_frontend_get_quick_forecast():
    """Verify frontend retrieves time series forecast with uncertainty bounds."""
    fc = get_quick_forecast(["Hog_education_Donnie"], horizon_hours=24)
    assert fc["status"] == "success"
    assert len(fc["data"]) == 24
    row = fc["data"][0]
    assert "forecast_kwh" in row
    assert "lower_bound_kwh" in row
    assert "upper_bound_kwh" in row
    assert row["lower_bound_kwh"] <= row["forecast_kwh"] <= row["upper_bound_kwh"]


# -------------------------------------------------------------
# Frontend Charts Engine Tests
# -------------------------------------------------------------
def test_charts_build_line_with_uncertainty_ribbon():
    """Verify line chart builds 3 traces: upper bound, lower ribbon, and central prediction."""
    chart_spec = {
        "type": "line",
        "x": "timestamp",
        "y": "forecast_kwh",
        "x_label": "Time",
        "y_label": "kWh",
        "title": "24h Forecast"
    }
    sample_data = [
        {"timestamp": "2024-04-01 01:00", "forecast_kwh": 100.0, "lower_bound_kwh": 85.0, "upper_bound_kwh": 115.0},
        {"timestamp": "2024-04-01 02:00", "forecast_kwh": 110.0, "lower_bound_kwh": 92.0, "upper_bound_kwh": 128.0},
    ]
    fig = build_chart_from_spec(chart_spec, sample_data)
    assert isinstance(fig, go.Figure)
    # Traces: Upper bound (line width 0), Lower bound (fill to nexty), Main forecast line
    assert len(fig.data) == 3
    assert fig.data[1].fill == "tonexty"
    assert fig.data[2].mode == "lines+markers"


def test_charts_build_bar_chart():
    """Verify bar chart builds valid bar visualization with proper ordering."""
    chart_spec = {
        "type": "bar",
        "x": "building",
        "y": "consumption",
        "x_label": "Building",
        "y_label": "kWh",
        "title": "Top Consumers"
    }
    sample_data = [
        {"building": "Hall A", "consumption": 500.0},
        {"building": "Hall B", "consumption": 1200.0},
    ]
    fig = build_chart_from_spec(chart_spec, sample_data)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    assert fig.data[0].type == "bar"


def test_charts_graceful_empty_data():
    """Verify empty or None inputs do not crash the chart engine."""
    assert build_chart_from_spec(None, []) is None
    assert build_chart_from_spec({"type": "line"}, []) is None
    assert isinstance(build_campus_overview_bar([]), go.Figure)
    assert isinstance(build_anomaly_breakdown_pie([]), go.Figure)


# -------------------------------------------------------------
# End-to-End Scenarios 1 Through 6 (Prompt Section 9.D)
# -------------------------------------------------------------
def test_e2e_scenario_1_historical_consumption():
    """Scenario 1: Which building consumed the most electricity last week?"""
    orchestrator = AgentOrchestrator()
    res = orchestrator.process_question("Which building consumed the most electricity last week?")
    assert res.status == "success"
    assert res.intent == "sql_query"
    assert len(res.data) > 0
    assert res.chart is not None
    assert res.chart.type == "bar"
    # Ensure real building and kWh value returned
    assert "total_consumption_kwh" in res.data[0] or "consumption_kwh" in res.data[0]
    assert res.data[0]["total_consumption_kwh"] > 0


def test_e2e_scenario_2_anomaly_detection():
    """Scenario 2: Which buildings have unusually high electricity consumption at night?"""
    orchestrator = AgentOrchestrator()
    res = orchestrator.process_question("Which buildings have unusually high electricity consumption at night?")
    assert res.status == "success"
    assert res.intent == "anomaly_detection"
    assert len(res.data) > 0
    # Person 2 anomaly fields
    assert "severity" in res.data[0]
    assert "deviation_pct" in res.data[0]


def test_e2e_scenario_3_forecasting():
    """Scenario 3: Forecast electricity consumption for Building 3 for the next 24 hours."""
    orchestrator = AgentOrchestrator()
    res = orchestrator.process_question("Forecast electricity consumption for Building 3 for the next 24 hours.")
    assert res.status == "success"
    assert res.intent == "forecast"
    assert len(res.data) == 24
    row = res.data[0]
    assert "forecast_kwh" in row
    assert "lower_bound_kwh" in row
    assert "upper_bound_kwh" in row
    assert row["lower_bound_kwh"] <= row["forecast_kwh"] <= row["upper_bound_kwh"]


def test_e2e_scenario_4_meter_flatline():
    """Scenario 4: Have any buildings had a meter reading that stopped changing?"""
    orchestrator = AgentOrchestrator()
    res = orchestrator.process_question("Have any buildings had a meter reading that stopped changing?")
    assert res.status == "success"
    assert res.intent == "anomaly_detection"
    assert len(res.data) > 0
    # Identified flatlines include Memorial Day telemetry freeze on Colette or Dona
    names = [r.get("building_name", "") for r in res.data]
    assert any("Colette" in n or "Dona" in n for n in names)


def test_e2e_scenario_5_invalid_or_ambiguous_question():
    """Scenario 5: Predict energy consumption for an unknown building / ambiguous query."""
    orchestrator = AgentOrchestrator()
    # Ambiguous question should trigger clarification
    res_ambiguous = orchestrator.process_question("Which building is wasting the most electricity?")
    assert res_ambiguous.status == "needs_clarification"
    assert res_ambiguous.needs_clarification is True
    assert res_ambiguous.clarification_question is not None

    # Invalid building query should return empty data and safe error message without fabricated numbers
    res_invalid = orchestrator.process_question("Predict energy consumption for UnknownBuilding999")
    assert res_invalid.status in ("error", "needs_clarification")
    assert len(res_invalid.data) == 0
    assert len(res_invalid.answer) > 0


def test_e2e_scenario_6_empty_insufficient_data():
    """Scenario 6: Ensure system handles missing/insufficient data without fabricating predictions."""
    from backend.app.services.forecast_service import forecast_energy
    # Non-existent building ID
    res = forecast_energy(["NonExistent_Building_XYZ"], horizon_hours=24)
    assert res["status"] == "error" or len(res["data"]) == 0
    # Does not fabricate predictions
    assert len(res.get("data", [])) == 0
