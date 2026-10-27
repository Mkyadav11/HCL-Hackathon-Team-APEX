"""
Test Suite for LLM Intent Routing, Ranking, and Result Preservation (Tests A through J)
Addresses Bug 1 (Top 5 Ranking Preservation) and Bug 2 (Greetings / Small Talk Isolation).
"""

import pytest
from unittest.mock import MagicMock
from backend.app.agent.orchestrator import AgentOrchestrator
from backend.app.agent.intent_router import QueryIntent
from backend.app.database.query_executor import QueryExecutionResult


@pytest.fixture
def orchestrator():
    return AgentOrchestrator()


# -------------------------------------------------------------------------
# Test A: Greeting
# -------------------------------------------------------------------------
def test_a_greeting(orchestrator):
    """Input: 'How are you?'
    Expected:
    - Intent is 'greeting'
    - No SQL query executed
    - No forecasting or anomaly detection called
    - Natural conversational response returned
    """
    res = orchestrator.process_question("How are you?")
    assert res.status == "success"
    assert res.intent == QueryIntent.GREETING.value
    assert res.sql_query is None
    assert len(res.data) == 0
    assert res.chart is None
    assert any(w in res.answer.lower() for w in ["doing well", "help you", "energy analytics"])


# -------------------------------------------------------------------------
# Test B: Top five buildings ranking
# -------------------------------------------------------------------------
def test_b_top_five_buildings(orchestrator):
    """Input: 'Rank the top 5 buildings with the highest energy consumption.'
    Expected:
    - Intent is 'sql_query'
    - Identifies top 5 ranking in descending order
    - Returns all 5 buildings in the data and in the final natural language answer
    """
    res = orchestrator.process_question("Rank the top 5 buildings with the highest energy consumption.")
    assert res.status == "success"
    assert res.intent == QueryIntent.SQL_QUERY.value
    assert len(res.data) == 5
    assert res.chart is not None
    assert res.chart.type == "bar"

    # Verify descending sort order
    consumptions = [row["total_consumption_kwh"] for row in res.data]
    assert consumptions == sorted(consumptions, reverse=True)

    # Verify all 5 buildings appear in the synthesized answer text
    assert "top 5 buildings" in res.answer.lower() or "5 buildings" in res.answer.lower()
    for row in res.data:
        assert row["name"] in res.answer


# -------------------------------------------------------------------------
# Test C: Top three buildings with lowest consumption
# -------------------------------------------------------------------------
def test_c_top_three_buildings_lowest(orchestrator):
    """Input: 'Show the three buildings with the lowest electricity consumption.'
    Expected:
    - Intent is 'sql_query'
    - Ascending sort order
    - Limit is 3
    - All 3 buildings returned and listed in order
    """
    res = orchestrator.process_question("Show the three buildings with the lowest electricity consumption.")
    assert res.status == "success"
    assert res.intent == QueryIntent.SQL_QUERY.value
    assert len(res.data) == 3

    # Verify ascending order
    consumptions = [row["total_consumption_kwh"] for row in res.data]
    assert consumptions == sorted(consumptions)

    # Verify all 3 buildings appear in answer
    for row in res.data:
        assert row["name"] in res.answer


# -------------------------------------------------------------------------
# Test D: Specific time period
# -------------------------------------------------------------------------
def test_d_specific_time_period(orchestrator):
    """Input: 'Rank the top 5 buildings by total electricity consumption last week.'
    Expected:
    - Identifies 'last week' time filter
    - Query uses 7-day boundary
    - Limit is 5
    - All 5 buildings returned
    """
    res = orchestrator.process_question("Rank the top 5 buildings by total electricity consumption last week.")
    assert res.status == "success"
    assert res.intent == QueryIntent.SQL_QUERY.value
    assert len(res.data) == 5
    assert "-7 days" in res.sql_query or "timestamp" in res.sql_query
    for row in res.data:
        assert row["name"] in res.answer


# -------------------------------------------------------------------------
# Test E: Ambiguous time period
# -------------------------------------------------------------------------
def test_e_ambiguous_time_period(orchestrator):
    """Input: 'Which building consumes the most energy?'
    Expected:
    - Follows documented default (total historical consumption with limit 1)
    - Returns single top consumer without fabricating arbitrary periods
    """
    res = orchestrator.process_question("Which building consumes the most energy?")
    assert res.status == "success"
    assert res.intent == QueryIntent.SQL_QUERY.value
    assert len(res.data) == 1
    assert "highest electricity consumption" in res.answer.lower()


# -------------------------------------------------------------------------
# Test F: Forecasting
# -------------------------------------------------------------------------
def test_f_forecasting(orchestrator):
    """Input: 'Forecast consumption for Building 3 for the next 24 hours.'
    Expected:
    - Intent is 'forecast'
    - Forecasting module is called
    - Returns 24 timestamped predicted values with 90% uncertainty bounds
    """
    res = orchestrator.process_question("Forecast consumption for Building 3 for the next 24 hours.")
    assert res.status == "success"
    assert res.intent == QueryIntent.FORECAST.value
    assert len(res.data) == 24
    assert res.sql_query is None
    assert any(w in res.answer.lower() for w in ["forecast", "expected", "confidence bounds"])
    row = res.data[0]
    assert "forecast_kwh" in row
    assert "lower_bound_kwh" in row
    assert "upper_bound_kwh" in row


# -------------------------------------------------------------------------
# Test G: Anomaly detection
# -------------------------------------------------------------------------
def test_g_anomaly_detection(orchestrator):
    """Input: 'Which buildings have unusually high consumption?'
    Expected:
    - Invokes Person 2 anomaly detection
    - Returns actual detected anomaly events without fabricating records
    """
    res = orchestrator.process_question("Which buildings have unusually high consumption?")
    assert res.status == "success"
    assert res.intent == QueryIntent.ANOMALY_DETECTION.value
    assert len(res.data) > 0
    assert "severity" in res.data[0]
    assert "deviation_pct" in res.data[0]


# -------------------------------------------------------------------------
# Test H: Query failure handling
# -------------------------------------------------------------------------
def test_h_query_failure(orchestrator):
    """Simulate a database failure and verify graceful error response."""
    # Mock executor to return failure
    mock_executor = MagicMock()
    mock_executor.execute_query.return_value = QueryExecutionResult(
        success=False,
        error_message="OperationalError: database disk image is malformed"
    )
    failing_orchestrator = AgentOrchestrator(executor=mock_executor)

    res = failing_orchestrator.process_question("Which building consumed the most electricity last week?")
    assert res.status == "error"
    assert len(res.data) == 0
    assert "An error occurred while executing the database query." in res.answer
    assert any("malformed" in w or "Execution failed" in w for w in res.warnings)


# -------------------------------------------------------------------------
# Test I: Result preservation
# -------------------------------------------------------------------------
def test_i_result_preservation(orchestrator):
    """Provide a 5-building dataset to _synthesize_answer and verify ALL 5 buildings appear."""
    mock_data = [
        {"name": "Alpha Tower", "total_consumption_kwh": 120500.5},
        {"name": "Beta Hall", "total_consumption_kwh": 95400.2},
        {"name": "Gamma Center", "total_consumption_kwh": 87200.0},
        {"name": "Delta Lab", "total_consumption_kwh": 65100.8},
        {"name": "Epsilon Complex", "total_consumption_kwh": 43200.1},
    ]

    answer = orchestrator._synthesize_answer("Rank the top 5 buildings by consumption", mock_data)

    # Must contain header and all 5 buildings in order
    assert "1. Alpha Tower: 120,500.50 kWh" in answer
    assert "2. Beta Hall: 95,400.20 kWh" in answer
    assert "3. Gamma Center: 87,200.00 kWh" in answer
    assert "4. Delta Lab: 65,100.80 kWh" in answer
    assert "5. Epsilon Complex: 43,200.10 kWh" in answer


# -------------------------------------------------------------------------
# Test J: Unsupported question
# -------------------------------------------------------------------------
def test_j_unsupported_question(orchestrator):
    """Input: 'Write a poem about the moon.'
    Expected:
    - Intent is 'unsupported'
    - No SQL executed
    - Courteously explains scope of energy copilot
    """
    res = orchestrator.process_question("Write a poem about the moon.")
    assert res.status == "success"
    assert res.intent == QueryIntent.UNSUPPORTED.value
    assert res.sql_query is None
    assert len(res.data) == 0
    assert "specialize in campus building energy analytics" in res.answer.lower()
