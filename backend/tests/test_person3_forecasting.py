import pytest
from backend.app.agent.orchestrator import AgentOrchestrator, orchestrator
from backend.app.services.forecast_service import (
    forecast_energy,
    generate_recommendations,
    suggest_building_action,
    validate_results,
)


def test_forecast_energy_single_valid_building():
    res = forecast_energy(building_ids=["Hog_education_Donnie"], horizon_hours=24)
    assert res["status"] == "success"
    assert res["horizon_hours"] == 24
    assert res["prediction_count"] == 24
    assert len(res["predictions"]) == 24

    first = res["predictions"][0]
    assert "timestamp" in first
    assert "forecast_kwh" in first
    assert "lower_bound_kwh" in first
    assert "upper_bound_kwh" in first
    assert first["lower_bound_kwh"] <= first["forecast_kwh"] <= first["upper_bound_kwh"]
    assert first["confidence_level"] == "90%"


def test_forecast_energy_multiple_buildings():
    buildings = ["Hog_education_Donnie", "Hog_education_Casandra"]
    res = forecast_energy(building_ids=buildings, horizon_hours=12)
    assert res["status"] == "success"
    assert res["prediction_count"] == 24  # 12 hours * 2 buildings

    b_ids = {p["building_id"] for p in res["predictions"]}
    assert "Hog_education_Donnie" in b_ids
    assert "Hog_education_Casandra" in b_ids


def test_forecast_energy_different_horizons():
    # 48 hours
    res_48 = forecast_energy(building_ids=["Hog_education_Donnie"], horizon_hours=48)
    assert res_48["status"] == "success"
    assert res_48["horizon_hours"] == 48
    assert len(res_48["predictions"]) == 48

    # 168 hours (7 days)
    res_168 = forecast_energy(building_ids=["Hog_education_Donnie"], horizon_hours=168)
    assert res_168["status"] == "success"
    assert res_168["horizon_hours"] == 168
    assert len(res_168["predictions"]) == 168


def test_forecast_energy_uncertainty_bounds_monotonicity():
    res = forecast_energy(building_ids=["Hog_education_Casandra"], horizon_hours=24)
    assert res["status"] == "success"
    for pred in res["predictions"]:
        assert pred["lower_bound_kwh"] >= 0.0
        assert pred["lower_bound_kwh"] <= pred["forecast_kwh"]
        assert pred["forecast_kwh"] <= pred["upper_bound_kwh"]
        assert pred["uncertainty_margin_kwh"] > 0.0


def test_forecast_energy_invalid_building_handled_gracefully():
    res = forecast_energy(building_ids=["NonExistent_Building_XYZ"], horizon_hours=24)
    assert res["status"] == "error"
    assert "No valid historical readings available" in res["error"]
    assert res["predictions"] == []


def test_person3_sanity_checks_validate_deviation():
    # Person 3 mathematical deviation check: ((138 - 100) / 100) * 100 = 38%
    claims = ["Electricity consumption increased by 38% compared to historical baseline."]
    res = validate_results(results={}, claims=claims)
    assert res["status"] == "success"
    assert res["verified"] is True
    assert len(res["checks"]) == 1
    assert res["checks"][0]["verified"] is True
    assert "formula_check" in res["checks"][0]
    assert res["checks"][0]["formula_check"]["valid"] is True


def test_person3_recommendations_action_suggestions():
    # Verify primary use specific action recommendations
    office_action = suggest_building_action("Office Tower")
    assert "HVAC schedules, lighting controls" in office_action

    edu_action = suggest_building_action("Education Hall")
    assert "classroom and common-area schedules" in edu_action

    assembly_action = suggest_building_action("Campus Auditorium Assembly")
    assert "Synchronize HVAC pre-cooling/heating with actual event bookings" in assembly_action

    lab_action = suggest_building_action("Industrial Research Lab")
    assert "fume hood" in lab_action.lower() or "laboratory air change" in lab_action.lower()


def test_person3_generate_recommendations():
    rec_res = generate_recommendations()
    assert rec_res["status"] == "success"
    assert rec_res["building_count"] > 0
    assert rec_res["total_potential_weekend_savings_kwh"] > 0.0
    for r in rec_res["recommendations"]:
        assert "building" in r
        assert "recommendation" in r
        assert "potential_weekend_savings_kwh" in r
        assert r["potential_weekend_savings_kwh"] >= 0.0


def test_orchestrator_forecast_tomorrow_routing():
    q = "What will tomorrow's electricity consumption be?"
    resp = orchestrator.process_question(q)
    assert resp.status == "success"
    assert resp.intent == "forecast"
    assert len(resp.data) > 0
    assert "forecast_kwh" in resp.data[0]
    assert "lower_bound_kwh" in resp.data[0]
    assert "upper_bound_kwh" in resp.data[0]
    assert resp.chart is not None
    assert resp.chart.type == "line"
    assert "24-Hour" in resp.chart.title or "Forecast" in resp.chart.title


def test_orchestrator_forecast_seven_days_routing():
    q = "Show me the expected consumption for the next seven days"
    resp = orchestrator.process_question(q)
    assert resp.status == "success"
    assert resp.intent == "forecast"
    assert len(resp.data) == 168  # 7 days * 24h
    assert "168" in resp.answer or "seven days" in q
    assert resp.chart.type == "line"


def test_orchestrator_recommendations_routing():
    q = "What actions could help reduce energy wastage?"
    resp = orchestrator.process_question(q)
    assert resp.status == "success"
    assert resp.intent == "recommendation"
    assert len(resp.data) > 0
    assert "potential_weekend_savings_kwh" in resp.data[0]
    assert resp.chart is not None
    assert resp.chart.type == "bar"
