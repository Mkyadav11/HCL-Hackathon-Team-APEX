import json
import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from backend.app.config import settings

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    """Abstract base class for interchangeable LLM providers."""

    @abstractmethod
    def generate_chat_completion(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        """Generate text completion from LLM provider."""
        pass


class OpenAILLMClient(BaseLLMClient):
    """OpenAI API implementation using official OpenAI SDK."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY must be provided or set in environment variables.")

        # Lazy import to keep dependency optional at runtime
        import openai
        self.client = openai.OpenAI(api_key=self.api_key)

    def generate_chat_completion(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=15.0,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise RuntimeError(f"LLM API failure: {str(e)}")


class MockRuleBasedLLMClient(BaseLLMClient):
    """Deterministic, rule-based mock LLM for testing, CI, and offline execution."""

    def generate_chat_completion(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.0,
        max_tokens: int = 1000,
    ) -> str:
        q = user_message.lower().strip()

        # Check for ambiguity
        if "wasting the most electricity" in q or "wasting most energy" in q:
            return json.dumps({
                "needs_clarification": True,
                "clarification_question": "Would you like me to compare electricity consumption during nights, weekends, or against each building's historical baseline?",
            })

        if "show me the consumption trend" in q and not any(f"building_{i}" in q for i in range(1, 16)):
            return json.dumps({
                "needs_clarification": True,
                "clarification_question": "Which building and time period would you like to analyze?",
            })

        # Check for intent classification requests
        if "intent_classification" in system_prompt.lower():
            if any(k in q for k in ["stopped reporting", "flatline", "abnormal", "unusually high", "anomaly", "zero reading"]):
                return json.dumps({"intent": "anomaly_detection"})
            if any(k in q for k in ["predict", "forecast", "tomorrow", "next week", "expected electricity"]):
                return json.dumps({"intent": "forecast"})
            if any(k in q for k in ["verify", "increased by", "sanity check", "does it agree"]):
                return json.dumps({"intent": "verification"})
            if any(k in q for k in ["save", "saving", "reduce", "recommendation", "efficiency"]):
                return json.dumps({"intent": "recommendation"})
            return json.dumps({"intent": "sql_query"})

        # 15 Hog building names map
        hog_names = {
            "donnie": "Hog_education_Donnie",
            "casandra": "Hog_education_Casandra",
            "quentin": "Hog_industrial_Quentin",
            "colette": "Hog_assembly_Colette",
            "rachael": "Hog_education_Rachael",
            "jeremy": "Hog_industrial_Jeremy",
            "mariah": "Hog_industrial_Mariah",
            "joanne": "Hog_industrial_Joanne",
            "jewel": "Hog_education_Jewel",
            "dona": "Hog_assembly_Dona",
            "madge": "Hog_education_Madge",
            "jordan": "Hog_education_Jordan",
            "jasmine": "Hog_assembly_Jasmine",
            "francisco": "Hog_lodging_Francisco",
            "morgan": "Hog_food_Morgan",
        }

        # Check for specific building mentioned
        target_bldg_id = None
        target_bldg_name = None
        for name, b_id in hog_names.items():
            if name in q:
                target_bldg_id = b_id
                target_bldg_name = name.title()
                break

        # Time range filter detection
        time_filter = ""
        if any(w in q for w in ["last day", "yesterday", "past 24 hours", "today"]):
            time_filter = "WHERE r.timestamp >= (SELECT datetime(MAX(timestamp), '-1 day') FROM energy_readings)"
        elif any(w in q for w in ["last week", "past 7 days", "past week"]):
            time_filter = "WHERE r.timestamp >= (SELECT datetime(MAX(timestamp), '-7 days') FROM energy_readings)"
        elif any(w in q for w in ["last month", "past 30 days"]):
            time_filter = "WHERE r.timestamp >= (SELECT datetime(MAX(timestamp), '-30 days') FROM energy_readings)"

        # Number words mapping for limits
        num_map = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
        }

        # Detect explicitly requested limit (e.g. "top 5", "lowest 3", "5 buildings", "three buildings")
        explicit_limit = None
        m_num = re.search(
            r"\b(?:top|first|lowest|least|highest|bottom|rank(?:ing)?|show(?: me)?)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b",
            q
        )
        if not m_num:
            m_num = re.search(
                r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:buildings?|facilities|meters?)\b",
                q
            )
        if m_num:
            token = m_num.group(1).lower()
            explicit_limit = num_map.get(token, int(token) if token.isdigit() else 5)

        # Lowest / least electricity consumption query
        if any(w in q for w in ["least electricity", "lowest electricity", "consumed the least", "minimum consumption", "lowest energy", "lowest consumption"]):
            limit_val = explicit_limit if explicit_limit is not None else 1
            where_clause = f"{time_filter} AND r.consumption_kwh > 0" if time_filter else "WHERE r.consumption_kwh > 0"
            title_text = f"{limit_val} Lowest Electricity Consumers" if limit_val > 1 else "Lowest Electricity Consumer"
            return json.dumps({
                "explanation": f"Calculates total electricity consumption for each building sorted in ascending order to find the {title_text.lower()}.",
                "sql": (
                    "SELECT b.name, b.building_id, ROUND(SUM(r.consumption_kwh), 2) AS total_consumption_kwh "
                    f"FROM energy_readings r "
                    f"JOIN buildings b ON r.building_id = b.building_id "
                    f"{where_clause} "
                    "GROUP BY b.name, b.building_id "
                    "ORDER BY total_consumption_kwh ASC "
                    f"LIMIT {limit_val}"
                ),
                "chart": {
                    "type": "bar",
                    "x": "name",
                    "y": "total_consumption_kwh",
                    "x_label": "Building",
                    "y_label": "Total Energy (kWh)",
                    "title": title_text
                }
            })

        # Most consumed / top ranking query
        if any(w in q for w in ["most electricity", "highest electricity", "consumed the most", "top consumer", "peak", "highest energy", "highest consumption", "rank", "ranking", "most energy"]):
            # Default to 1 if asking for single top building, or explicit limit if specified (e.g. top 5)
            if explicit_limit is not None:
                limit_val = explicit_limit
            elif any(w in q for w in ["all buildings", "compare"]):
                limit_val = 15
            else:
                limit_val = 1

            where_clause = f" {time_filter}" if time_filter else ""
            title_text = f"Top {limit_val} Electricity Consumers" if limit_val > 1 else "Top Electricity Consumer"
            return json.dumps({
                "explanation": f"Calculates total electricity consumption for each building sorted in descending order to identify the {title_text.lower()}.",
                "sql": (
                    "SELECT b.name, b.building_id, ROUND(SUM(r.consumption_kwh), 2) AS total_consumption_kwh "
                    f"FROM energy_readings r "
                    f"JOIN buildings b ON r.building_id = b.building_id "
                    f"{where_clause} "
                    "GROUP BY b.name, b.building_id "
                    "ORDER BY total_consumption_kwh DESC "
                    f"LIMIT {limit_val}"
                ),
                "chart": {
                    "type": "bar",
                    "x": "name",
                    "y": "total_consumption_kwh",
                    "x_label": "Building",
                    "y_label": "Total Energy (kWh)",
                    "title": title_text
                }
            })

        # Compare electricity consumption across all buildings or by primary use
        if "by type" in q or "by use" in q or "primary use" in q:
            return json.dumps({
                "explanation": "Aggregates total electricity consumption grouped by building primary use category.",
                "sql": (
                    "SELECT b.primary_use, ROUND(SUM(r.consumption_kwh), 2) AS total_consumption_kwh, "
                    "COUNT(DISTINCT b.building_id) as building_count "
                    "FROM energy_readings r "
                    "JOIN buildings b ON r.building_id = b.building_id "
                    "GROUP BY b.primary_use "
                    "ORDER BY total_consumption_kwh DESC "
                    "LIMIT 10"
                ),
                "chart": {
                    "type": "bar",
                    "x": "primary_use",
                    "y": "total_consumption_kwh",
                    "x_label": "Primary Use",
                    "y_label": "Total Energy (kWh)",
                    "title": "Energy Consumption by Building Type"
                }
            })

        if "compare" in q or "all buildings" in q:
            where_clause = f" {time_filter}" if time_filter else ""
            return json.dumps({
                "explanation": "Aggregates total electricity consumption for all campus buildings for comparison.",
                "sql": (
                    "SELECT b.name, b.building_id, ROUND(SUM(r.consumption_kwh), 2) AS total_consumption_kwh "
                    f"FROM energy_readings r "
                    f"JOIN buildings b ON r.building_id = b.building_id "
                    f"{where_clause} "
                    "GROUP BY b.name, b.building_id "
                    "ORDER BY total_consumption_kwh DESC "
                    "LIMIT 15"
                ),
                "chart": {
                    "type": "bar",
                    "x": "name",
                    "y": "total_consumption_kwh",
                    "x_label": "Building",
                    "y_label": "Total Consumption (kWh)",
                    "title": "Building Consumption Comparison"
                }
            })

        # Hourly or daily trend for a building
        match = re.search(r"building[_\s]?(\d+)", q)
        if target_bldg_id or match or "trend" in q or "hourly" in q:
            b_id = target_bldg_id or (f"Building_{int(match.group(1)):02d}" if match else "Hog_education_Donnie")
            b_title = target_bldg_name or b_id
            return json.dumps({
                "explanation": f"Retrieves hourly electricity consumption trend for {b_title}.",
                "sql": (
                    f"SELECT timestamp, consumption_kwh "
                    f"FROM energy_readings "
                    f"WHERE building_id = '{b_id}' "
                    f"ORDER BY timestamp ASC "
                    f"LIMIT 168"
                ),
                "chart": {
                    "type": "line",
                    "x": "timestamp",
                    "y": "consumption_kwh",
                    "x_label": "Timestamp",
                    "y_label": "Consumption (kWh)",
                    "title": f"Hourly Consumption Trend for {b_title}"
                }
            })

        # Default fallback query
        return json.dumps({
            "explanation": "Retrieves recent energy consumption summary across buildings.",
            "sql": (
                "SELECT b.name, ROUND(AVG(r.consumption_kwh), 2) AS avg_hourly_kwh, "
                "ROUND(SUM(r.consumption_kwh), 2) AS total_kwh "
                "FROM energy_readings r "
                "JOIN buildings b ON r.building_id = b.building_id "
                "GROUP BY b.name "
                "ORDER BY total_kwh DESC "
                "LIMIT 10"
            ),
            "chart": {
                "type": "bar",
                "x": "name",
                "y": "total_kwh",
                "x_label": "Building",
                "y_label": "Total Energy (kWh)",
                "title": "Campus Energy Summary"
            }
        })


def get_llm_client() -> BaseLLMClient:
    """Factory function returning the active LLM client based on configuration."""
    api_key = settings.OPENAI_API_KEY
    if api_key and api_key.strip() and not api_key.startswith("mock"):
        try:
            return OpenAILLMClient(api_key=api_key)
        except Exception as e:
            logger.warning(f"Could not initialize OpenAILLMClient ({e}), falling back to mock LLM client.")
    return MockRuleBasedLLMClient()
