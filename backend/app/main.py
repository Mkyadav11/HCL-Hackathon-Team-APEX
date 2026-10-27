import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import router as api_router
from backend.app.config import settings
from backend.app.database.seed_data import seed_database

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure SQLite database is seeded on startup if not present."""
    if settings.DB_TYPE.lower() == "sqlite":
        db_path = Path(settings.SQLITE_PATH)
        if not db_path.exists():
            print(f"Database not found at {db_path}. Initializing with seed data...")
            seed_database(str(db_path))
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "AI-Powered Energy Analytics Copilot backend orchestrating Natural Language-to-SQL, "
        "SQLGlot query validation, meter anomaly detection, and consumption forecasting."
    ),
    lifespan=lifespan,
)

# Enable CORS for Streamlit / Frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API endpoints under /api/v1
app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/", summary="Root Endpoint")
def root():
    return {
        "message": "Welcome to the Energy Analytics Copilot Backend",
        "docs_url": "/docs",
        "health_url": f"{settings.API_PREFIX}/health",
        "query_endpoint": f"{settings.API_PREFIX}/chat/query",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
