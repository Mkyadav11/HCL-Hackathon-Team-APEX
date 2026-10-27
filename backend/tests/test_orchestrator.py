import pytest
from backend.app.agent.orchestrator import AgentOrchestrator
from backend.app.agent.sql_generator import SQLGenerator
from backend.app.agent.sql_validator import SQLValidator
from backend.app.database.query_executor import SafeQueryExecutor


@pytest.fixture
def orchestrator():
    validator = SQLValidator(dialect="sqlite")
    generator = SQLGenerator(validator=validator)
    executor = SafeQueryExecutor()
    return AgentOrchestrator(generator=generator, executor=executor)


def test_orchestrator_most_electricity_question(orchestrator):
    q = "Which building consumed the most electricity last week?"
    resp = orchestrator.process_question(q)

    assert resp.status == "success"
    assert resp.intent == "sql_query"
    assert resp.needs_clarification is False
    assert len(resp.data) > 0
    assert "Data & Computing Center" in resp.answer or "highest" in resp.answer
    assert resp.chart is not None
    assert resp.chart.type == "bar"
    assert resp.sql_query is not None


def test_orchestrator_compare_buildings_question(orchestrator):
    q = "Compare electricity consumption across all buildings this month."
    resp = orchestrator.process_question(q)

    assert resp.status == "success"
    assert resp.intent == "sql_query"
    assert len(resp.data) > 1
    assert resp.chart is not None
    assert resp.chart.type == "bar"


def test_orchestrator_anomaly_routing_person2(orchestrator):
    q = "Which meters have stopped reporting?"
    resp = orchestrator.process_question(q)

    assert resp.status == "success"
    assert resp.intent == "anomaly_detection"
    assert "Person 2" in resp.warnings[0]
    assert resp.needs_clarification is False


def test_orchestrator_night_spike_anomaly_routing_person2(orchestrator):
    q = "Which buildings are consuming unusually high electricity at night?"
    resp = orchestrator.process_question(q)

    assert resp.status == "success"
    assert resp.intent == "anomaly_detection"
    assert "Person 2" in resp.warnings[0]


def test_orchestrator_forecast_routing_person3(orchestrator):
    q = "What is the expected electricity consumption for tomorrow?"
    resp = orchestrator.process_question(q)

    assert resp.status == "success"
    assert resp.intent == "forecast"
    assert len(resp.data) > 0
    assert "forecast_kwh" in resp.data[0]
    assert "lower_bound_kwh" in resp.data[0]
    assert "upper_bound_kwh" in resp.data[0]
    assert resp.chart is not None
    assert resp.chart.type == "line"


def test_orchestrator_savings_recommendations_routing(orchestrator):
    q = "How much electricity could we potentially save by reducing weekend consumption?"
    resp = orchestrator.process_question(q)

    assert resp.status == "success"
    assert resp.intent == "recommendation"
    assert len(resp.data) > 0
    assert "potential_weekend_savings_kwh" in resp.data[0]
    assert resp.chart is not None


def test_orchestrator_clarification_handling(orchestrator):
    q = "Which building is wasting the most electricity?"
    resp = orchestrator.process_question(q)

    assert resp.status == "needs_clarification"
    assert resp.needs_clarification is True
    assert resp.clarification_question is not None
    assert "nights, weekends, or against each building's historical baseline" in resp.clarification_question
    assert resp.data == []


def test_orchestrator_empty_question(orchestrator):
    resp = orchestrator.process_question("   ")
    assert resp.status == "error"
    assert resp.data == []
