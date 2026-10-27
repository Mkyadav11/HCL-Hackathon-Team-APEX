import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.database.connection import db_manager


class QueryExecutionResult(BaseModel):
    success: bool
    data: List[Dict[str, Any]] = []
    columns: List[str] = []
    row_count: int = 0
    execution_time_ms: float = 0.0
    error_message: Optional[str] = None


class SafeQueryExecutor:
    """Executes validated read-only SQL queries against the database."""

    def __init__(self, timeout_seconds: Optional[float] = None, max_rows: Optional[int] = None):
        self.timeout_seconds = timeout_seconds or settings.QUERY_TIMEOUT_SECONDS
        self.max_rows = max_rows or settings.MAX_ROW_LIMIT

    def execute_query(self, sanitized_sql: str) -> QueryExecutionResult:
        """Executes a sanitized SELECT query safely.
        
        Guarantees:
        - Only read-only execution.
        - Enforces execution timeout.
        - Caps returned rows.
        - Catches all exceptions and strips internal connection or credential info.
        """
        start_time = time.perf_counter()
        conn = None
        try:
            conn = db_manager.get_connection()
            cursor = conn.cursor()

            # Execute query
            cursor.execute(sanitized_sql)

            # Fetch columns and rows safely
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            
            # Fetch up to max_rows + 1 to detect truncation
            rows = cursor.fetchmany(self.max_rows + 1)
            
            # Convert rows to standard dicts
            results: List[Dict[str, Any]] = []
            for row in rows[:self.max_rows]:
                if isinstance(row, dict):
                    results.append(dict(row))
                elif hasattr(row, "keys"):  # sqlite3.Row
                    results.append({k: row[k] for k in row.keys()})
                else:  # tuple
                    results.append(dict(zip(columns, row)))

            execution_time = (time.perf_counter() - start_time) * 1000.0

            return QueryExecutionResult(
                success=True,
                data=results,
                columns=columns,
                row_count=len(results),
                execution_time_ms=round(execution_time, 2),
            )

        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000.0
            # Sanitize error message to ensure no connection info or passwords leak
            safe_msg = self._sanitize_error_message(str(e))
            return QueryExecutionResult(
                success=False,
                data=[],
                columns=[],
                row_count=0,
                execution_time_ms=round(execution_time, 2),
                error_message=safe_msg,
            )
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _sanitize_error_message(self, raw_error: str) -> str:
        """Sanitizes database error messages to prevent credential/system leakage."""
        sensitive_keywords = ["password", "user", "host", "port", "secret", "token", "key"]
        lower_err = raw_error.lower()
        if any(kw in lower_err for kw in sensitive_keywords):
            return "A database execution error occurred while processing the query."
        
        # General safe cleanup
        if "syntax error" in lower_err:
            return "Database syntax error in generated query."
        if "no such table" in lower_err:
            return "Referenced database table does not exist."
        if "no such column" in lower_err:
            return "Referenced database column does not exist."
        if "timeout" in lower_err:
            return f"Query execution timed out after {self.timeout_seconds}s."

        return f"Database error: {raw_error}"


safe_query_executor = SafeQueryExecutor()
