"""
EnergySense API Client
Connects Person 4's Streamlit frontend to Person 1's FastAPI backend orchestrator.
Handles HTTP requests, timeouts, graceful degradation, and structured response parsing.
"""

import os
import sys
from pathlib import Path
import requests
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


def check_backend_health(base_url: str = DEFAULT_BACKEND_URL, timeout: float = 2.0) -> bool:
    """Check if the FastAPI backend service is reachable and healthy."""
    url = f"{base_url.rstrip('/')}/api/v1/health"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("status") == "healthy"
        return False
    except Exception:
        return False


def query_copilot(
    question: str,
    base_url: str = DEFAULT_BACKEND_URL,
    timeout: float = 30.0
) -> Dict[str, Any]:
    """
    Send a natural language question to Person 1's AI Copilot API.
    
    Endpoint: POST /api/v1/chat/query
    Payload: {"question": question}
    
    Returns:
        Structured ChatQueryResponse dictionary matching backend contract.
    """
    url = f"{base_url.rstrip('/')}/api/v1/chat/query"
    payload = {"question": question}

    try:
        response = requests.post(url, json=payload, timeout=timeout)
        if response.status_code == 200:
            return response.json()
        
        # Non-200 HTTP response
        return {
            "status": "error",
            "intent": "unknown",
            "answer": f"Backend returned HTTP {response.status_code}: {response.text}",
            "data": [],
            "chart": None,
            "sql_query": None,
            "warnings": [f"HTTP error {response.status_code} from {url}"],
            "needs_clarification": False,
            "clarification_question": None,
            "execution_time_ms": 0.0,
        }
    except requests.exceptions.ConnectionError:
        # Graceful fallback: Attempt direct in-process query via backend orchestrator
        try:
            from backend.app.agent.orchestrator import AgentOrchestrator
            orchestrator = AgentOrchestrator()
            result = orchestrator.process_question(question)
            resp_dict = result.model_dump() if hasattr(result, "model_dump") else result.dict()
            resp_dict["warnings"] = resp_dict.get("warnings", []) + [
                f"Notice: HTTP server at {base_url} is unreachable; answered via local in-process orchestrator."
            ]
            return resp_dict
        except Exception as local_err:
            return {
                "status": "error",
                "intent": "connection_error",
                "answer": (
                    f"Unable to connect to Energy Analytics Copilot backend at {base_url}. "
                    f"Please ensure the backend server is running via:\n\n"
                    f"`python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload`\n\n"
                    f"Error detail: {str(local_err)}"
                ),
                "data": [],
                "chart": None,
                "sql_query": None,
                "warnings": [f"Connection refused at {url}"],
                "needs_clarification": False,
                "clarification_question": None,
                "execution_time_ms": 0.0,
            }
    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "intent": "timeout",
            "answer": f"Request to backend timed out after {timeout} seconds.",
            "data": [],
            "chart": None,
            "sql_query": None,
            "warnings": ["Query processing timed out."],
            "needs_clarification": False,
            "clarification_question": None,
            "execution_time_ms": timeout * 1000,
        }
    except Exception as e:
        return {
            "status": "error",
            "intent": "unknown",
            "answer": f"An unexpected error occurred: {str(e)}",
            "data": [],
            "chart": None,
            "sql_query": None,
            "warnings": [str(e)],
            "needs_clarification": False,
            "clarification_question": None,
            "execution_time_ms": 0.0,
        }


def get_building_summaries(base_url: str = DEFAULT_BACKEND_URL) -> List[Dict[str, Any]]:
    """Retrieve building summary data from backend or database service."""
    try:
        from backend.app.services.energy_service import get_building_summary
        res = get_building_summary()
        return res.get("data", [])
    except Exception:
        return []


def get_recent_anomalies(limit: int = 10, base_url: str = DEFAULT_BACKEND_URL) -> List[Dict[str, Any]]:
    """Retrieve detected anomaly events from Person 2's anomaly service."""
    try:
        from backend.app.services.anomaly_service import detect_anomalies
        res = detect_anomalies(limit=limit)
        return res.get("anomalies", res.get("data", []))
    except Exception:
        return []


def get_quick_forecast(building_ids: Optional[List[str]] = None, horizon_hours: int = 24) -> Dict[str, Any]:
    """Retrieve forecast results from Person 3's forecasting service."""
    try:
        from backend.app.services.forecast_service import forecast_energy
        res = forecast_energy(building_ids=building_ids, horizon_hours=horizon_hours)
        if "data" not in res and "predictions" in res:
            res["data"] = res["predictions"]
        return res
    except Exception as e:
        return {"status": "error", "error": str(e), "data": []}
