import pytest
from backend.app.agent.llm_client import BaseLLMClient, MockRuleBasedLLMClient
from backend.app.agent.sql_generator import SQLGenerator
from backend.app.agent.sql_validator import SQLValidator


class MaliciousLLMClient(BaseLLMClient):
    """Simulates an adversarial or compromised LLM returning destructive SQL."""
    def generate_chat_completion(self, system_prompt: str, user_message: str, temperature: float = 0.0, max_tokens: int = 1000) -> str:
        return '{"explanation": "Deleting records", "sql": "DELETE FROM energy_readings WHERE id > 0"}'


class GarbageLLMClient(BaseLLMClient):
    """Simulates an LLM returning unparseable garbage text."""
    def generate_chat_completion(self, system_prompt: str, user_message: str, temperature: float = 0.0, max_tokens: int = 1000) -> str:
        return "I am unable to answer this question at the moment. Please try again."


class FailingAPIClient(BaseLLMClient):
    """Simulates an LLM API network error or timeout."""
    def generate_chat_completion(self, system_prompt: str, user_message: str, temperature: float = 0.0, max_tokens: int = 1000) -> str:
        raise RuntimeError("Connection timed out to LLM gateway.")


def test_generate_most_consumed_query():
    gen = SQLGenerator(llm_client=MockRuleBasedLLMClient(), validator=SQLValidator(dialect="sqlite"))
    res = gen.generate_sql("Which building consumed the most electricity last week?")
    assert res.success is True
    assert res.needs_clarification is False
    assert "SELECT" in res.sanitized_sql.upper()
    assert "LIMIT" in res.sanitized_sql.upper()
    assert res.chart_spec is not None
    assert res.chart_spec.type == "bar"


def test_generate_compare_buildings_query():
    gen = SQLGenerator(llm_client=MockRuleBasedLLMClient(), validator=SQLValidator(dialect="sqlite"))
    res = gen.generate_sql("Compare electricity consumption across all buildings this month")
    assert res.success is True
    assert "GROUP BY" in res.sanitized_sql.upper()
    assert "energy_readings" in res.validation.tables_used


def test_ambiguous_question_triggers_clarification():
    gen = SQLGenerator(llm_client=MockRuleBasedLLMClient(), validator=SQLValidator(dialect="sqlite"))
    res = gen.generate_sql("Which building is wasting the most electricity?")
    assert res.success is True
    assert res.needs_clarification is True
    assert res.clarification_question is not None
    assert "nights, weekends, or against each building's historical baseline" in res.clarification_question


def test_malicious_llm_sql_is_blocked():
    gen = SQLGenerator(llm_client=MaliciousLLMClient(), validator=SQLValidator(dialect="sqlite"))
    res = gen.generate_sql("Reset all building meter readings")
    assert res.success is False
    assert "SQL validation error" in res.error_message
    assert res.sanitized_sql is None


def test_garbage_llm_response_handled_safely():
    gen = SQLGenerator(llm_client=GarbageLLMClient(), validator=SQLValidator(dialect="sqlite"))
    res = gen.generate_sql("Give me building data")
    assert res.success is False
    assert "Could not parse a valid structured response" in res.error_message


def test_failing_llm_api_handled_safely():
    gen = SQLGenerator(llm_client=FailingAPIClient(), validator=SQLValidator(dialect="sqlite"))
    res = gen.generate_sql("How much energy was used?")
    assert res.success is False
    assert "LLM service error" in res.error_message
