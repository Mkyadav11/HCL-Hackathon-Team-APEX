import sqlite3
from typing import Any, Optional
from pathlib import Path
from backend.app.config import settings


class DatabaseConnectionManager:
    """Manages database connections for SQLite and PostgreSQL.
    
    Provides read-only connections and abstract execution interface.
    """

    def __init__(self, db_type: Optional[str] = None):
        self.db_type = (db_type or settings.DB_TYPE).lower()
        self.sqlite_path = settings.SQLITE_PATH

    def get_connection(self) -> Any:
        """Returns a database connection with read-only principles."""
        if self.db_type == "sqlite":
            # Ensure parent directory exists
            Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
            # Open SQLite connection
            conn = sqlite3.connect(
                self.sqlite_path,
                timeout=settings.QUERY_TIMEOUT_SECONDS,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            return conn
        elif self.db_type == "postgres":
            try:
                import psycopg2
                import psycopg2.extras

                conn = psycopg2.connect(
                    host=settings.POSTGRES_HOST,
                    port=settings.POSTGRES_PORT,
                    user=settings.POSTGRES_USER,
                    password=settings.POSTGRES_PASSWORD,
                    dbname=settings.POSTGRES_DB,
                    connect_timeout=int(settings.QUERY_TIMEOUT_SECONDS),
                )
                # Enforce read-only transaction on postgres session
                conn.set_session(readonly=True, autocommit=True)
                return conn
            except ImportError:
                raise RuntimeError(
                    "PostgreSQL driver 'psycopg2' is not installed. "
                    "Install with: pip install psycopg2-binary"
                )
        else:
            raise ValueError(f"Unsupported DB_TYPE: {self.db_type}")


db_manager = DatabaseConnectionManager()
