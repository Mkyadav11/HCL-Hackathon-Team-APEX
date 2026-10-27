import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    json_data = response.json()
    assert "docs_url" in json_data


def test_health_check_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_schema_endpoint():
    response = client.get("/api/v1/schema")
    assert response.status_code == 200
    data = response.json()
    assert "buildings" in data["tables"]
    assert "energy_readings" in data["tables"]


def test_chat_query_top_building():
    payload = {"question": "Which building consumed the most electricity last week?"}
    response = client.post("/api/v1/chat/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["intent"] == "sql_query"
    assert len(data["data"]) > 0
    assert data["chart"] is not None
    assert data["chart"]["type"] == "bar"


def test_chat_query_comparison():
    payload = {"question": "Compare electricity consumption across all buildings this month"}
    response = client.post("/api/v1/chat/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["data"]) > 1


def test_chat_query_clarification():
    payload = {"question": "Which building is wasting the most electricity?"}
    response = client.post("/api/v1/chat/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "needs_clarification"
    assert data["needs_clarification"] is True
    assert data["clarification_question"] is not None


def test_chat_query_anomaly_routing():
    payload = {"question": "Which meters have stopped reporting?"}
    response = client.post("/api/v1/chat/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["intent"] == "anomaly_detection"


def test_chat_query_forecast_routing():
    payload = {"question": "What is the expected electricity consumption for tomorrow?"}
    response = client.post("/api/v1/chat/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["intent"] == "forecast"
    assert len(data["data"]) > 0
    # Check that Person 3 uncertainty bounds and chart spec are present
    assert "predicted_kwh" in data["data"][0]
    assert "lower_bound_kwh" in data["data"][0]
    assert "upper_bound_kwh" in data["data"][0]
    assert data["chart"]["type"] == "line"


def test_chat_query_recommendations_routing():
    payload = {"question": "What actions could help reduce energy wastage?"}
    response = client.post("/api/v1/chat/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["intent"] == "recommendation"
    assert len(data["data"]) > 0
    assert "recommended_action" in data["data"][0]
    assert data["chart"]["type"] == "bar"
