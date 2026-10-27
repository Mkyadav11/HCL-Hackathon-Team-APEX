from fastapi import APIRouter, HTTPException, status
from backend.app.agent.orchestrator import orchestrator
from backend.app.database.schema_context import schema_context
from backend.app.schemas.responses import ChatQueryRequest, ChatQueryResponse

router = APIRouter()


@router.post(
    "/chat/query",
    response_model=ChatQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Process natural language energy questions",
    description=(
        "Interprets natural language queries, validates AST SQL queries, "
        "and routes to anomaly detection or forecasting modules."
    ),
)
async def query_energy_copilot(payload: ChatQueryRequest) -> ChatQueryResponse:
    """Primary chat endpoint for Energy Analytics Copilot."""
    try:
        response = orchestrator.process_question(
            question=payload.question,
            user_context=payload.user_context,
        )
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected internal error occurred: {str(e)}",
        )


@router.get(
    "/health",
    summary="Service Health Check",
    description="Returns backend service status and operational metadata.",
)
async def health_check():
    return {
        "status": "healthy",
        "service": "Energy Analytics Copilot",
        "version": "0.1.0",
        "database": "connected",
    }


@router.get(
    "/schema",
    summary="Inspect Database Schema",
    description="Returns allowed tables and column metadata for frontend and integrations.",
)
async def get_schema():
    return {
        "tables": schema_context.tables,
        "whitelist": {k: list(v) for k, v in schema_context.get_allowed_schema_whitelist().items()},
    }
