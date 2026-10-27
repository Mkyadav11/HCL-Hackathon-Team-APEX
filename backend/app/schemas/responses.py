from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class ChartSpec(BaseModel):
    """Specification for frontend rendering with Plotly."""
    type: Literal["bar", "line", "scatter", "pie", "indicator", "table"] = "bar"
    x: Optional[str] = None
    y: Optional[str] = None
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    title: Optional[str] = None
    series_name: Optional[str] = None


class ChatQueryRequest(BaseModel):
    """Request payload for user question."""
    question: str = Field(..., min_length=1, description="Natural language question from user")
    user_context: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Optional contextual filters or user settings"
    )


class ChatQueryResponse(BaseModel):
    """Structured response conforming to Person 4 frontend requirements."""
    status: Literal["success", "needs_clarification", "error"] = "success"
    intent: str = Field(..., description="Detected intent of the query")
    answer: str = Field(..., description="Human-readable explanation of findings")
    data: List[Dict[str, Any]] = Field(default_factory=list, description="Structured query or analytical data")
    chart: Optional[ChartSpec] = Field(default=None, description="Plotly chart specification")
    sql_query: Optional[str] = Field(default=None, description="Generated and validated SQL query, if applicable")
    warnings: List[str] = Field(default_factory=list, description="Any warnings, caveats, or assumptions")
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    execution_time_ms: Optional[float] = None
