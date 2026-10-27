import logging
import re
from enum import Enum
from typing import Optional, Tuple
from backend.app.agent.llm_client import BaseLLMClient, get_llm_client

logger = logging.getLogger(__name__)


class QueryIntent(str, Enum):
    GREETING = "greeting"
    SQL_QUERY = "sql_query"
    ENERGY_QUERY = "sql_query"  # Canonical alias
    ANOMALY_DETECTION = "anomaly_detection"
    FORECAST = "forecast"
    VERIFICATION = "verification"
    RECOMMENDATION = "recommendation"
    CLARIFICATION = "clarification"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class IntentRouter:
    """Routes user queries deterministically and safely to the appropriate analytical module."""

    # Conversational greeting and introductory patterns
    GREETING_PATTERNS = [
        r"^(hi|hello|hey|howdy|greetings|good\s+(morning|afternoon|evening|day))[\s!.,?]*$",
        r"^(how\s+are\s+you|how\s+are\s+you\s+doing|how's\s+it\s+going|how\s+do\s+you\s+do)[\s!.,?]*$",
        r"^(who\s+are\s+you|what\s+are\s+you|what\s+can\s+you\s+do|tell\s+me\s+about\s+yourself|help)[\s!.,?]*$",
        r"^(thanks|thank\s+you|thx|cheers)[\s!.,?]*$",
        r"^(nice\s+to\s+meet\s+you|what's\s+up)[\s!.,?]*$",
    ]

    # Ambiguous phrases requiring prompt clarification
    AMBIGUOUS_PATTERNS = [
        (
            r"\b(wasting|waste)\b.*\b(electricity|energy|power)\b",
            "Would you like me to compare electricity consumption during nights, weekends, or against each building's historical baseline?"
        ),
        (
            r"^(show me|display|plot)\s+(the\s+)?(consumption\s+)?trend\s*$",
            "Which building and time period would you like to analyze?"
        ),
    ]

    # Deterministic keywords for specialized team member modules
    ANOMALY_KEYWORDS = [
        "stopped reporting",
        "stop reporting",
        "not reporting",
        "stopped changing",
        "stop changing",
        "not changing",
        "flatline",
        "abnormal",
        "unusually high",
        "anomaly",
        "anomalies",
        "zero reading",
        "meter failure",
    ]

    FORECAST_KEYWORDS = [
        "predict",
        "prediction",
        "forecast",
        "forecasting",
        "tomorrow",
        "expected electricity",
        "expected consumption",
        "expected energy",
        "next week",
        "next seven days",
        "next 7 days",
        "next 24 hours",
        "next 48 hours",
        "future consumption",
        "likely to consume",
    ]

    RECOMMENDATION_KEYWORDS = [
        "save",
        "saving",
        "savings",
        "reduce",
        "reduction",
        "recommendation",
        "recommend",
        "conserve",
        "efficiency",
    ]

    VERIFICATION_KEYWORDS = [
        "verify",
        "verification",
        "sanity check",
        "increased by",
        "decreased by",
        "does it agree",
    ]

    # Domain keywords that indicate a question is relevant to campus energy analytics
    ENERGY_KEYWORDS = [
        "energy", "electricity", "power", "consumption", "kwh", "kilowatt", "kw",
        "meter", "meters", "reading", "readings", "building", "buildings", "campus",
        "facility", "facilities", "hall", "complex", "usage", "load", "demand",
        "peak", "baseline", "rank", "ranking", "highest", "lowest", "most", "least",
        "compare", "comparison", "trend", "hourly", "daily", "weekly", "monthly",
        "top", "bottom", "average", "total", "sum", "historical"
    ]

    CAMPUS_BUILDING_NAMES = [
        "donnie", "casandra", "quentin", "colette", "rachael", "jeremy", "mariah",
        "joanne", "jewel", "dona", "madge", "jordan", "jasmine", "francisco", "morgan",
        "hog"
    ]

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm_client = llm_client or get_llm_client()

    def route_intent(self, question: str) -> Tuple[QueryIntent, Optional[str]]:
        """Determines the appropriate intent and any immediate clarification message."""
        normalized = question.lower().strip()

        # Step 1: Detect greetings and small talk (conversational, no tools)
        for pattern in self.GREETING_PATTERNS:
            if re.search(pattern, normalized):
                logger.info(f"Intent classified as GREETING for query: '{question}'")
                return QueryIntent.GREETING, None

        # Step 2: Check for ambiguous inputs needing immediate clarification
        for pattern, clarification_msg in self.AMBIGUOUS_PATTERNS:
            if re.search(pattern, normalized):
                logger.info(f"Intent classified as CLARIFICATION for query: '{question}'")
                return QueryIntent.CLARIFICATION, clarification_msg

        # Step 3: Check specialized modules
        if any(kw in normalized for kw in self.ANOMALY_KEYWORDS):
            logger.info(f"Intent classified as ANOMALY_DETECTION for query: '{question}'")
            return QueryIntent.ANOMALY_DETECTION, None

        if any(kw in normalized for kw in self.FORECAST_KEYWORDS):
            logger.info(f"Intent classified as FORECAST for query: '{question}'")
            return QueryIntent.FORECAST, None

        if any(kw in normalized for kw in self.RECOMMENDATION_KEYWORDS):
            logger.info(f"Intent classified as RECOMMENDATION for query: '{question}'")
            return QueryIntent.RECOMMENDATION, None

        if any(kw in normalized for kw in self.VERIFICATION_KEYWORDS):
            logger.info(f"Intent classified as VERIFICATION for query: '{question}'")
            return QueryIntent.VERIFICATION, None

        # Step 4: Check if query relates to energy analytics
        is_energy_related = (
            any(kw in normalized for kw in self.ENERGY_KEYWORDS) or
            any(name in normalized for name in self.CAMPUS_BUILDING_NAMES) or
            bool(re.search(r"building\s*(\d+|[a-z]+)", normalized))
        )

        if is_energy_related:
            logger.info(f"Intent classified as SQL_QUERY for query: '{question}'")
            return QueryIntent.SQL_QUERY, None

        # Step 5: Unrelated or out-of-domain questions
        logger.info(f"Intent classified as UNSUPPORTED for query: '{question}'")
        return QueryIntent.UNSUPPORTED, None


intent_router = IntentRouter()
