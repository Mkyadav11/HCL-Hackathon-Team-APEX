import os
from pathlib import Path
from pydantic import BaseModel, Field


class Settings(BaseModel):
    PROJECT_NAME: str = "Energy Analytics Copilot"
    VERSION: str = "0.1.0"
    API_PREFIX: str = "/api/v1"
    
    # Environment
    ENV: str = Field(default=os.getenv("ENV", "development"))
    
    # LLM Settings
    OPENAI_API_KEY: str = Field(default=os.getenv("OPENAI_API_KEY", ""))
    OPENAI_MODEL: str = Field(default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    LLM_TEMPERATURE: float = Field(default=0.0)
    
    # Database Settings
    DB_TYPE: str = Field(default=os.getenv("DB_TYPE", "sqlite"))  # "sqlite" or "postgres"
    SQLITE_PATH: str = Field(
        default=os.getenv(
            "SQLITE_PATH",
            str(Path(__file__).resolve().parent.parent / "database" / "energy_data.db")
        )
    )
    POSTGRES_HOST: str = Field(default=os.getenv("POSTGRES_HOST", "localhost"))
    POSTGRES_PORT: int = Field(default=int(os.getenv("POSTGRES_PORT", "5432")))
    POSTGRES_USER: str = Field(default=os.getenv("POSTGRES_USER", "postgres_readonly"))
    POSTGRES_PASSWORD: str = Field(default=os.getenv("POSTGRES_PASSWORD", ""))
    POSTGRES_DB: str = Field(default=os.getenv("POSTGRES_DB", "energy_analytics"))
    
    # Safety & Resource Limits
    QUERY_TIMEOUT_SECONDS: float = Field(default=float(os.getenv("QUERY_TIMEOUT_SECONDS", "5.0")))
    MAX_ROW_LIMIT: int = Field(default=int(os.getenv("MAX_ROW_LIMIT", "500")))
    DEFAULT_ROW_LIMIT: int = Field(default=int(os.getenv("DEFAULT_ROW_LIMIT", "100")))


settings = Settings()
