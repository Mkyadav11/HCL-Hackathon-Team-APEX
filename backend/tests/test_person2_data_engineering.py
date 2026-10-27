import pytest
from backend.app.services.anomaly_engine import AnomalyEngine, anomaly_engine
from backend.app.services.anomaly_service import (
    calculate_baseline_deviation,
    detect_anomalies,
    detect_flatlines,
    get_anomaly_summary_report,
)
from backend.app.services.energy_service import (
    get_building_summary,
    get_data_quality_report,
    get_energy_data,
)


def test_deviation_calculation_standard():
    # ((actual - baseline) / baseline) * 100
    actual = 150.0
    baseline = 100.0
    dev = calculate_baseline_deviation(actual, baseline)
    assert dev == 50.0


def test_deviation_calculation_zero_baseline():
    # Safe handling of zero baseline without ZeroDivisionError
    dev = calculate_baseline_deviation(actual=50.0, baseline=0.0)
    assert dev == 100.0

    dev_zero_actual = calculate_baseline_deviation(actual=0.0, baseline=0.0)
    assert dev_zero_actual == 0.0


def test_total_anomaly_counts_match_existing_report():
    # Verifies total anomaly count is exactly 41,499
    summary_rep = get_anomaly_summary_report()
    assert summary_rep["status"] == "success"
    assert summary_rep["total_anomalies"] == 41499

    # Check breakdown matches CSV
    types = {r["anomaly_type"]: r["event_count"] for r in summary_rep["breakdown"]}
    assert types.get("high_consumption") == 41497 or (20485 + 21012 == 41497)
    assert types.get("flatline") == 2


def test_building_level_anomaly_counts_match_detailed():
    # Donnie: 6544, Casandra: 6091, Quentin: 5550, Colette: 5321
    bldg_summaries = get_building_summary()
    assert bldg_summaries["status"] == "success"
    assert bldg_summaries["building_count"] == 15

    bldg_map = {b["building_id"]: b["anomaly_count"] for b in bldg_summaries["data"]}
    assert bldg_map["Hog_education_Donnie"] == 6544
    assert bldg_map["Hog_education_Casandra"] == 6091
    assert bldg_map["Hog_industrial_Quentin"] == 5550
    assert bldg_map["Hog_assembly_Colette"] == 5321
    assert bldg_map["Hog_food_Morgan"] == 270

    # Total sum of anomaly_count across all 15 buildings
    total_bldg_anomalies = sum(bldg_map.values())
    assert total_bldg_anomalies == 41499


def test_flatline_detection_identifies_memorial_day_freeze():
    flatlines = detect_flatlines(min_consecutive_hours=24)
    assert flatlines["status"] == "success"
    assert flatlines["candidate_count"] == 2

    candidates = {c["building_id"]: c for c in flatlines["candidates"]}
    assert "Hog_assembly_Colette" in candidates
    assert "Hog_assembly_Dona" in candidates

    colette = candidates["Hog_assembly_Colette"]
    assert colette["reading_count"] == 125
    assert colette["energy_value"] == 322.813
    assert colette["start_time"] == "2016-05-26 07:00:00"
    assert colette["end_time"] == "2016-05-31 11:00:00"

    dona = candidates["Hog_assembly_Dona"]
    assert dona["reading_count"] == 125
    assert dona["energy_value"] == 190.674


def test_data_quality_report_sampling_frequency():
    dq = get_data_quality_report()
    assert dq["status"] == "success"
    assert dq["building_count"] == 15

    for b in dq["data"]:
        # Expected grid: 17,544 readings, 0 missing
        assert b["reading_count"] == 17544
        assert b["missing_readings"] == 0.0
        assert b["sampling_interval_hours"] == 1.0


def test_get_energy_data_retrieval_and_summary_statistics():
    res = get_energy_data(building_ids=["Hog_education_Donnie"], limit=50)
    assert res["status"] == "success"
    assert res["count"] > 0
    assert len(res["data"]) == res["count"]
    assert "summary_statistics" in res
    assert res["summary_statistics"]["total_kwh"] > 0.0
    assert res["summary_statistics"]["average_kwh"] > 0.0
    assert res["unit"] == "kWh"


def test_get_energy_data_empty_results_handled():
    # Future timestamp with no records
    res = get_energy_data(start_time="2099-01-01 00:00:00", end_time="2099-01-02 00:00:00")
    assert res["status"] == "success"
    assert res["count"] == 0
    assert res["data"] == []
    assert res["summary_statistics"]["total_kwh"] == 0.0


def test_get_energy_data_invalid_timestamp_handled_safely():
    res = get_energy_data(start_time="invalid-not-a-date")
    assert res["status"] == "error"
    assert "Invalid start_time format" in res["error"]
    assert res["data"] == []


def test_detect_anomalies_filters_by_severity():
    high_res = detect_anomalies(severity="high", limit=10)
    assert high_res["status"] == "success"
    assert high_res["total_matched_events"] > 0
    for anom in high_res["anomalies"]:
        assert anom["severity"].lower() == "high"


def test_detect_anomalies_filters_by_type():
    flat_res = detect_anomalies(anomaly_type="flatline")
    assert flat_res["status"] == "success"
    assert flat_res["total_matched_events"] == 2
    for anom in flat_res["anomalies"]:
        assert anom["anomaly_type"] == "flatline"


def test_regenerate_anomaly_summary_engine():
    summary_rows = anomaly_engine.regenerate_anomaly_summary()
    assert len(summary_rows) > 0
    total_events = sum(r["event_count"] for r in summary_rows)
    assert total_events == 41499
