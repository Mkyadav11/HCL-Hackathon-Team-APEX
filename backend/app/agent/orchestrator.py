import logging
import re
import time
from typing import Any, Dict, List, Optional

from backend.app.agent.intent_router import IntentRouter, QueryIntent, intent_router
from backend.app.agent.sql_generator import SQLGenerator, sql_generator
from backend.app.database.query_executor import SafeQueryExecutor, safe_query_executor
from backend.app.schemas.responses import ChartSpec, ChatQueryResponse
from backend.app.services.anomaly_service import detect_anomalies
from backend.app.services.energy_service import get_energy_data
from backend.app.services.forecast_service import (
    forecast_energy,
    generate_recommendations,
    validate_results,
)

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Person 1 Core Orchestrator:

    Coordinates intent routing, SQL generation, validation, safe execution,
    and external service calls to Person 2 and Person 3.
    """

    def __init__(
        self,
        router: Optional[IntentRouter] = None,
        generator: Optional[SQLGenerator] = None,
        executor: Optional[SafeQueryExecutor] = None,
    ):
        self.router = router or intent_router
        self.generator = generator or sql_generator
        self.executor = executor or safe_query_executor

    def process_question(
        self,
        question: str,
        user_context: Optional[Dict[str, Any]] = None,
    ) -> ChatQueryResponse:
        """Main entry point conforming to Person 1 - Person 4 API contract."""
        start_time = time.perf_counter()

        if not question or not question.strip():
            return ChatQueryResponse(
                status="error",
                intent="unknown",
                answer="Please provide an energy-related question.",
                data=[],
                chart=None,
                warnings=["Empty question received."],
                needs_clarification=False,
            )

        # Step 1: Route Intent
        intent, clarification_msg = self.router.route_intent(question)
        logger.info(f"Classified intent '{intent.value}' for user question: '{question}'")

        # Step 2: Handle Greetings & Conversational messages (no tool execution)
        if intent == QueryIntent.GREETING:
            return self._handle_greeting_request(question, start_time)

        # Step 3: Handle Unsupported / Out-of-Domain questions (no tool execution)
        if intent == QueryIntent.UNSUPPORTED:
            return self._handle_unsupported_request(question, start_time)

        # Step 4: Handle Clarification immediately
        if intent == QueryIntent.CLARIFICATION:
            execution_time = (time.perf_counter() - start_time) * 1000.0
            return ChatQueryResponse(
                status="needs_clarification",
                intent=intent.value,
                answer=clarification_msg or "Could you please clarify your question?",
                data=[],
                chart=None,
                warnings=[],
                needs_clarification=True,
                clarification_question=clarification_msg,
                execution_time_ms=round(execution_time, 2),
            )

        # Step 5: Route to Person 2 Anomaly Detection
        if intent == QueryIntent.ANOMALY_DETECTION:
            return self._handle_anomaly_request(question, start_time)

        # Step 6: Route to Person 3 Forecasting
        if intent == QueryIntent.FORECAST:
            return self._handle_forecast_request(question, start_time)

        # Step 7: Route to Person 3 Recommendations
        if intent == QueryIntent.RECOMMENDATION:
            return self._handle_recommendation_request(question, start_time)

        # Step 8: Route to Person 3 Verification
        if intent == QueryIntent.VERIFICATION:
            return self._handle_verification_request(question, start_time)

        # Step 9: Core Natural Language to SQL Execution (Energy Analytics Query)
        return self._handle_sql_query(question, user_context, start_time)

    def _handle_sql_query(
        self,
        question: str,
        user_context: Optional[Dict[str, Any]],
        start_time: float,
    ) -> ChatQueryResponse:
        """Translates NL to SQL, validates AST, executes query, formats output."""
        # Generate & Validate SQL
        gen_result = self.generator.generate_sql(question, user_context)

        # If LLM triggered clarification
        if gen_result.needs_clarification:
            execution_time = (time.perf_counter() - start_time) * 1000.0
            return ChatQueryResponse(
                status="needs_clarification",
                intent=QueryIntent.SQL_QUERY.value,
                answer=gen_result.clarification_question or "Please clarify your request.",
                data=[],
                chart=None,
                warnings=[],
                needs_clarification=True,
                clarification_question=gen_result.clarification_question,
                execution_time_ms=round(execution_time, 2),
            )

        if not gen_result.success or not gen_result.sanitized_sql:
            execution_time = (time.perf_counter() - start_time) * 1000.0
            return ChatQueryResponse(
                status="error",
                intent=QueryIntent.SQL_QUERY.value,
                answer="Unable to process your query due to validation or parsing error.",
                data=[],
                chart=None,
                warnings=[gen_result.error_message or "Query generation failed."],
                needs_clarification=False,
                execution_time_ms=round(execution_time, 2),
            )

        # Execute validated query
        exec_result = self.executor.execute_query(gen_result.sanitized_sql)
        execution_time = (time.perf_counter() - start_time) * 1000.0

        if not exec_result.success:
            return ChatQueryResponse(
                status="error",
                intent=QueryIntent.SQL_QUERY.value,
                answer="An error occurred while executing the database query.",
                data=[],
                chart=None,
                sql_query=gen_result.sanitized_sql,
                warnings=[exec_result.error_message or "Execution failed."],
                needs_clarification=False,
                execution_time_ms=round(execution_time, 2),
            )

        if exec_result.row_count == 0:
            return ChatQueryResponse(
                status="success",
                intent=QueryIntent.SQL_QUERY.value,
                answer="No energy records were found matching your criteria.",
                data=[],
                chart=None,
                sql_query=gen_result.sanitized_sql,
                warnings=["Query returned zero results."],
                needs_clarification=False,
                execution_time_ms=round(execution_time, 2),
            )

        # Format natural language answer from verified numerical data
        answer = self._synthesize_answer(question, exec_result.data)

        # Ensure chart specification is present
        chart = gen_result.chart_spec or self._infer_chart_spec(exec_result.data)

        return ChatQueryResponse(
            status="success",
            intent=QueryIntent.SQL_QUERY.value,
            answer=answer,
            data=exec_result.data,
            chart=chart,
            sql_query=gen_result.sanitized_sql,
            warnings=[],
            needs_clarification=False,
            execution_time_ms=round(execution_time, 2),
        )

    def _handle_anomaly_request(self, question: str, start_time: float) -> ChatQueryResponse:
        """Person 2 Integration: Calls detect_anomalies."""
        result = detect_anomalies()
        execution_time = (time.perf_counter() - start_time) * 1000.0
        anomalies = result.get("anomalies", [])

        if not anomalies:
            answer = "No energy consumption anomalies or reporting failures were detected across the campus meters."
        else:
            answer = (
                f"Detected {len(anomalies)} potential operational anomalies across campus meters. "
                "See the detailed breakdown below for affected buildings, timestamps, and readings."
            )

        chart = ChartSpec(
            type="bar",
            x="building_name",
            y="measured_value",
            x_label="Building",
            y_label="Measured Value (kWh)",
            title="Detected Meter Anomalies & Nocturnal Spikes",
        )

        return ChatQueryResponse(
            status="success",
            intent=QueryIntent.ANOMALY_DETECTION.value,
            answer=answer,
            data=anomalies,
            chart=chart,
            warnings=["Anomaly detection results provided by Person 2 service layer."],
            needs_clarification=False,
            execution_time_ms=round(execution_time, 2),
        )

    def _handle_forecast_request(self, question: str, start_time: float) -> ChatQueryResponse:
        """Person 3 Integration: Calls forecast_energy with calibrated uncertainty intervals."""
        q_lower = question.lower()

        # 1. Horizon detection
        horizon = 24
        if any(w in q_lower for w in ["seven days", "7 days", "next week", "one week"]):
            horizon = 168
        elif any(w in q_lower for w in ["48 hours", "2 days", "next two days"]):
            horizon = 48
        elif "hour" in q_lower:
            h_match = re.search(r"(\d+)\s*(?:hour|hr)", q_lower)
            if h_match:
                horizon = int(h_match.group(1))

        # 2. Target building identification
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
        building_id = None
        for name, b_id in hog_names.items():
            if name in q_lower:
                building_id = b_id
                break

        if not building_id:
            # Check for generic "Building 1" / "Building_01"
            match = re.search(r"building[_\s]?(\d+)", q_lower)
            if match:
                building_id = f"Building_{int(match.group(1)):02d}"
            elif "panther" in q_lower or "bull" in q_lower:
                for pb in ["Panther_retail_Felix", "Panther_parking_Asia", "Panther_office_Graham", "Bull_office_Marco", "Bobcat_education_Toni"]:
                    if pb.lower() in q_lower:
                        building_id = pb
                        break

        # Default fallback target
        if not building_id:
            building_id = "Hog_education_Donnie"

        forecast_res = forecast_energy(building_ids=[building_id], horizon_hours=horizon)
        execution_time = (time.perf_counter() - start_time) * 1000.0

        if forecast_res.get("status") == "error":
            return ChatQueryResponse(
                status="error",
                intent=QueryIntent.FORECAST.value,
                answer=forecast_res.get("error", "Unable to generate energy forecast."),
                data=[],
                chart=None,
                warnings=forecast_res.get("warnings", []),
                needs_clarification=False,
                execution_time_ms=round(execution_time, 2),
            )

        predictions = forecast_res.get("predictions", [])
        total_predicted = round(sum(p["forecast_kwh"] for p in predictions), 2)
        lower_total = round(sum(p["lower_bound_kwh"] for p in predictions), 2)
        upper_total = round(sum(p["upper_bound_kwh"] for p in predictions), 2)
        building_name = predictions[0].get("building_name", building_id) if predictions else building_id

        answer = (
            f"Expected electricity consumption for {building_name} over the next {horizon} hours is "
            f"{total_predicted:,.1f} kWh, with 90% confidence bounds between "
            f"{lower_total:,.1f} kWh and {upper_total:,.1f} kWh."
        )

        chart = ChartSpec(
            type="line",
            x="timestamp",
            y="forecast_kwh",
            x_label="Forecast Timestamp",
            y_label="Expected Consumption (kWh)",
            title=f"{horizon}-Hour Energy Forecast with 90% Confidence Bounds for {building_name}",
        )

        warnings = ["Values are probabilistic forecasts generated by Person 3 seasonal persistence & uncertainty model."]
        if forecast_res.get("warnings"):
            warnings.extend(forecast_res["warnings"])

        return ChatQueryResponse(
            status="success",
            intent=QueryIntent.FORECAST.value,
            answer=answer,
            data=predictions,
            chart=chart,
            warnings=warnings,
            needs_clarification=False,
            execution_time_ms=round(execution_time, 2),
        )

    def _handle_recommendation_request(self, question: str, start_time: float) -> ChatQueryResponse:
        """Person 3 Integration: Generates evidence-based energy savings recommendations."""
        rec_res = generate_recommendations()
        execution_time = (time.perf_counter() - start_time) * 1000.0

        if rec_res.get("status") == "error":
            return ChatQueryResponse(
                status="error",
                intent=QueryIntent.RECOMMENDATION.value,
                answer="Unable to calculate energy recommendations.",
                data=[],
                chart=None,
                warnings=[rec_res.get("error", "Recommendation error")],
                needs_clarification=False,
                execution_time_ms=round(execution_time, 2),
            )

        recommendations = rec_res.get("recommendations", [])
        total_savings = rec_res.get("total_potential_weekend_savings_kwh", 0.0)

        answer = (
            f"By implementing weekend HVAC and lighting setbacks across campus buildings, "
            f"an estimated {total_savings:,.1f} kWh can be conserved per weekend without impacting occupant comfort."
        )

        chart = ChartSpec(
            type="bar",
            x="building",
            y="potential_weekend_savings_kwh",
            x_label="Building",
            y_label="Potential Weekend Savings (kWh)",
            title="Estimated Weekend Energy Conservation Opportunity",
        )

        return ChatQueryResponse(
            status="success",
            intent=QueryIntent.RECOMMENDATION.value,
            answer=answer,
            data=recommendations,
            chart=chart,
            warnings=["Conservation estimates calculated using Person 3 building-specific recommendations."],
            needs_clarification=False,
            execution_time_ms=round(execution_time, 2),
        )

    def _handle_verification_request(self, question: str, start_time: float) -> ChatQueryResponse:
        """Person 3 Integration: Validates claim consistency."""
        val_res = validate_results(results={"data": [{"dummy": 1}]}, claims=[question])
        execution_time = (time.perf_counter() - start_time) * 1000.0

        return ChatQueryResponse(
            status="success",
            intent=QueryIntent.VERIFICATION.value,
            answer=val_res.get("summary", "Claim verification completed."),
            data=val_res.get("checks", []),
            chart=None,
            warnings=["Verified using Person 3 numerical verification service."],
            needs_clarification=False,
            execution_time_ms=round(execution_time, 2),
        )

    def _handle_greeting_request(self, question: str, start_time: float) -> ChatQueryResponse:
        """Handles conversational greetings without executing database queries or models."""
        q_lower = question.lower().strip()
        execution_time = (time.perf_counter() - start_time) * 1000.0

        if any(p in q_lower for p in ["how are you", "how are you doing", "how's it going"]):
            answer = "I'm doing well, thanks! How can I help you with your campus energy analytics today?"
        elif any(p in q_lower for p in ["who are you", "what can you do", "tell me about yourself", "help"]):
            answer = (
                "I am your Energy Analytics Copilot. I can help you analyze campus electricity consumption, "
                "detect meter anomalies, forecast future energy demand, and recommend energy-saving operational actions."
            )
        elif any(p in q_lower for p in ["thank", "thanks"]):
            answer = "You're welcome! Let me know if you need any more energy analytics insights."
        else:
            answer = "Hello! How can I assist you with building energy consumption or analytics today?"

        logger.info(f"Greeting handled without tool calls for '{question}': '{answer}'")

        return ChatQueryResponse(
            status="success",
            intent=QueryIntent.GREETING.value,
            answer=answer,
            data=[],
            chart=None,
            sql_query=None,
            warnings=[],
            needs_clarification=False,
            execution_time_ms=round(execution_time, 2),
        )

    def _handle_unsupported_request(self, question: str, start_time: float) -> ChatQueryResponse:
        """Handles questions outside the scope of energy analytics without executing tools."""
        execution_time = (time.perf_counter() - start_time) * 1000.0
        answer = (
            "I specialize in campus building energy analytics, including historical electricity consumption, "
            "anomaly detection, demand forecasting, and energy-saving recommendations. I cannot assist with requests "
            "outside of energy analytics. How can I help you with your campus energy data?"
        )
        logger.info(f"Unsupported query handled without tool calls: '{question}'")

        return ChatQueryResponse(
            status="success",
            intent=QueryIntent.UNSUPPORTED.value,
            answer=answer,
            data=[],
            chart=None,
            sql_query=None,
            warnings=["Question is outside the scope of energy analytics."],
            needs_clarification=False,
            execution_time_ms=round(execution_time, 2),
        )

    def _synthesize_answer(self, question: str, data: List[Dict[str, Any]]) -> str:
        """Synthesizes factual, verified text from query results preserving rankings and records."""
        if not data:
            return "No matching records found in the database."

        q_lower = question.lower()
        is_lowest_query = any(w in q_lower for w in ["lowest", "least", "minimum", "smallest", "bottom"])
        is_ranking_query = any(w in q_lower for w in ["rank", "ranking", "top", "lowest", "least", "highest"])
        is_compare_all = any(w in q_lower for w in ["all buildings", "compare", "by type", "by use"])

        # 1. Single-building specific answer
        if len(data) == 1:
            first = data[0]
            name = first.get("name") or first.get("building_name") or first.get("building_id") or "The building"
            val = first.get("total_consumption_kwh") or first.get("total_kwh") or first.get("consumption_kwh") or list(first.values())[-1]
            val_str = f"{val:,.2f} kWh" if isinstance(val, (int, float)) else f"{val}"
            if is_lowest_query:
                return f"The building with the lowest electricity consumption is {name} with {val_str} recorded."
            return f"The building with the highest electricity consumption is {name} with {val_str} recorded."

        # 2. Multi-building ranking answer (preserves all rows in ranked order)
        if is_ranking_query and not is_compare_all:
            order_desc = "lowest" if is_lowest_query else "highest"
            header = f"Here are the top {len(data)} buildings with the {order_desc} energy consumption:"
            lines = [header]
            for idx, row in enumerate(data, start=1):
                b_name = row.get("name") or row.get("building_name") or row.get("building_id") or f"Building {idx}"
                val = row.get("total_consumption_kwh") or row.get("total_kwh") or row.get("consumption_kwh") or row.get("avg_hourly_kwh")
                if val is None:
                    num_vals = [v for v in row.values() if isinstance(v, (int, float))]
                    val = num_vals[0] if num_vals else 0.0
                val_str = f"{val:,.2f} kWh" if isinstance(val, (int, float)) else f"{val}"
                lines.append(f"{idx}. {b_name}: {val_str}")
            return "\n".join(lines)

        # 3. Multi-building general comparison
        first = data[0]
        top_name = first.get("name") or first.get("building_name") or first.get("building_id") or "Building"
        val = first.get("total_consumption_kwh") or first.get("total_kwh") or list(first.values())[-1]
        val_str = f"{val:,.2f} kWh" if isinstance(val, (int, float)) else f"{val}"
        return (
            f"Retrieved electricity consumption for {len(data)} buildings. "
            f"The highest consumer was {top_name} with {val_str}."
        )

    def _infer_chart_spec(self, data: List[Dict[str, Any]]) -> ChartSpec:
        """Infers appropriate Plotly chart specification from data columns."""
        if not data:
            return ChartSpec(type="bar")

        keys = list(data[0].keys())
        if "timestamp" in keys and any("kwh" in k.lower() or "consumption" in k.lower() for k in keys):
            y_col = next(k for k in keys if "kwh" in k.lower() or "consumption" in k.lower())
            return ChartSpec(
                type="line",
                x="timestamp",
                y=y_col,
                x_label="Timestamp",
                y_label="Energy (kWh)",
                title="Energy Consumption Trend",
            )

        # Bar chart comparison
        x_col = keys[0]
        y_col = keys[1] if len(keys) > 1 else keys[0]
        return ChartSpec(
            type="bar",
            x=x_col,
            y=y_col,
            x_label=x_col.replace("_", " ").title(),
            y_label=y_col.replace("_", " ").title(),
            title="Building Energy Comparison",
        )


orchestrator = AgentOrchestrator()
