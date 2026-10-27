import json
import logging
import re
from typing import Any, Dict, Optional
from pydantic import BaseModel

from backend.app.agent.llm_client import BaseLLMClient, get_llm_client
from backend.app.agent.sql_validator import SQLValidator, ValidationResult
from backend.app.database.schema_context import schema_context
from backend.app.schemas.responses import ChartSpec

logger = logging.getLogger(__name__)


class SQLGenerationResult(BaseModel):
    success: bool
    sql: Optional[str] = None
    sanitized_sql: Optional[str] = None
    explanation: Optional[str] = None
    chart_spec: Optional[ChartSpec] = None
    validation: Optional[ValidationResult] = None
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    error_message: Optional[str] = None


class SQLGenerator:
    """Converts natural language questions into safe, validated SQL queries."""

    SYSTEM_PROMPT_TEMPLATE = """You are an expert energy analytics SQL assistant for a university campus.
Your task is to convert natural language energy questions into safe, read-only SQL queries.

{schema_context}

Output ONLY valid JSON matching this exact structure:
{{
  "needs_clarification": false,
  "clarification_question": null,
  "explanation": "Brief explanation of how the query computes the answer",
  "sql": "SELECT ...",
  "chart": {{
    "type": "bar" | "line" | "table",
    "x": "column_for_x_axis",
    "y": "column_for_y_axis",
    "x_label": "Human readable X-axis label",
    "y_label": "Human readable Y-axis label",
    "title": "Chart title"
  }}
}}

Rules:
1. ONLY generate a single SELECT statement.
2. NEVER generate INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, or administrative queries.
3. If the user's question is fundamentally ambiguous (e.g., 'Which building is wasting energy?' without criteria), set 'needs_clarification': true and provide 'clarification_question'.
4. Ensure all table and column names exist in the schema.
5. Hourly consumption is interval data in kWh. Summing hourly consumption yields total kWh.
6. If the user requests a specific number of items (e.g., 'top 5', 'lowest 3'), ALWAYS reflect that exact number in the LIMIT clause (e.g. LIMIT 5). If asking for a single highest/lowest building without specifying a count, use LIMIT 1.
7. Sort ORDER BY ... DESC for highest, most, peak, or top rankings. Sort ORDER BY ... ASC for lowest, least, or minimum rankings.
8. For comparisons across all buildings or unconstrained queries, use a sensible default limit (e.g., LIMIT 15).
"""

    def __init__(
        self,
        llm_client: Optional[BaseLLMClient] = None,
        validator: Optional[SQLValidator] = None,
    ):
        self.llm_client = llm_client or get_llm_client()
        self.validator = validator or SQLValidator()

    def generate_sql(
        self,
        question: str,
        user_context: Optional[Dict[str, Any]] = None,
        max_retries: int = 1,
    ) -> SQLGenerationResult:
        """Translates natural language question into validated SQL query."""
        schema_prompt = schema_context.get_llm_schema_prompt()
        system_prompt = self.SYSTEM_PROMPT_TEMPLATE.format(schema_context=schema_prompt)

        context_str = f"\nUser Context: {json.dumps(user_context)}" if user_context else ""
        user_prompt = f"Question: {question}{context_str}"

        # First attempt
        raw_response = ""
        try:
            raw_response = self.llm_client.generate_chat_completion(
                system_prompt=system_prompt,
                user_message=user_prompt,
                temperature=0.0,
            )
        except Exception as e:
            logger.error(f"LLM API failure during SQL generation: {e}")
            return SQLGenerationResult(
                success=False,
                error_message=f"LLM service error: {str(e)}",
            )

        parsed_plan = self._extract_json(raw_response)
        if not parsed_plan:
            # Fallback: try extracting raw SQL statement directly
            raw_sql = self._extract_sql(raw_response)
            if raw_sql:
                parsed_plan = {"sql": raw_sql, "explanation": "Extracted SQL query from response"}
            else:
                return SQLGenerationResult(
                    success=False,
                    error_message="Could not parse a valid structured response from the language model.",
                )

        # Check if clarification is needed
        if parsed_plan.get("needs_clarification"):
            return SQLGenerationResult(
                success=True,
                needs_clarification=True,
                clarification_question=parsed_plan.get(
                    "clarification_question",
                    "Could you please specify which buildings or time range you would like to examine?"
                ),
                explanation="Question requires clarification.",
            )

        generated_sql = parsed_plan.get("sql", "").strip()
        if not generated_sql:
            return SQLGenerationResult(
                success=False,
                error_message="Language model did not provide an SQL query.",
            )

        # Validate SQL with SQLValidator
        validation = self.validator.validate(generated_sql)

        # Self-correction loop if validation fails and retries remain
        if not validation.is_valid and max_retries > 0:
            logger.warning(f"SQL validation failed: {validation.error_message}. Attempting self-correction.")
            correction_prompt = (
                f"{user_prompt}\n"
                f"Your previous query was: {generated_sql}\n"
                f"Validation failed with error: {validation.error_message}\n"
                f"Please fix the error and output only the corrected JSON."
            )
            try:
                retry_response = self.llm_client.generate_chat_completion(
                    system_prompt=system_prompt,
                    user_message=correction_prompt,
                    temperature=0.0,
                )
                retry_plan = self._extract_json(retry_response)
                if retry_plan and retry_plan.get("sql"):
                    generated_sql = retry_plan["sql"].strip()
                    validation = self.validator.validate(generated_sql)
                    parsed_plan = retry_plan
            except Exception as e:
                logger.error(f"Correction retry failed: {e}")

        if not validation.is_valid:
            return SQLGenerationResult(
                success=False,
                sql=generated_sql,
                validation=validation,
                error_message=f"SQL validation error: {validation.error_message}",
            )

        # Build ChartSpec if chart metadata is present
        chart_spec = None
        raw_chart = parsed_plan.get("chart")
        if isinstance(raw_chart, dict):
            try:
                chart_spec = ChartSpec(**raw_chart)
            except Exception:
                chart_spec = ChartSpec(type="bar")

        return SQLGenerationResult(
            success=True,
            sql=generated_sql,
            sanitized_sql=validation.sanitized_sql,
            explanation=parsed_plan.get("explanation", "Query generated successfully."),
            chart_spec=chart_spec,
            validation=validation,
        )

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extracts JSON from text, stripping markdown code fences."""
        cleaned = text.strip()
        # Remove markdown code block if present
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try finding the first '{' and last '}'
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(cleaned[start : end + 1])
                except json.JSONDecodeError:
                    pass
        return None

    def _extract_sql(self, text: str) -> Optional[str]:
        """Extracts SQL from text if JSON parsing fails."""
        # Check for ```sql ... ```
        match = re.search(r"```(?:sql)?\s*(SELECT\b[\s\S]*?)```", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        # Check for raw SELECT statement
        match = re.search(r"\b(SELECT\b[\s\S]+)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None


sql_generator = SQLGenerator()
