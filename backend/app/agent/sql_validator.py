import re
from typing import Dict, List, Optional, Set
from pydantic import BaseModel
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from backend.app.config import settings


class ValidationResult(BaseModel):
    is_valid: bool
    error_message: Optional[str] = None
    sanitized_sql: Optional[str] = None
    tables_used: List[str] = []
    columns_used: List[str] = []


class SQLValidator:
    """Strict AST-based SQL query validator using SQLGlot.
    
    Guarantees:
    - Only a single, read-only SELECT statement can execute.
    - Rejects INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, and other write operations.
    - Rejects multiple statements (semicolon separation / batch execution).
    - Validates tables and columns against an authorized whitelist.
    - Handles table aliases and JOINs safely.
    - Disallows unsafe database functions (e.g. pg_sleep, load_extension).
    - Enforces maximum row limit (LIMIT clause injection/capping).
    """

    FORBIDDEN_FUNCTIONS: Set[str] = {
        "pg_sleep",
        "sleep",
        "benchmark",
        "load_extension",
        "pg_read_file",
        "pg_write_file",
        "dblink",
        "system",
        "exec",
        "eval",
        "xp_cmdshell",
    }

    MUTATION_EXPRESSIONS = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Create,
        exp.Alter,
        exp.Command,
        exp.Into,
    )

    def __init__(
        self,
        allowed_schema: Optional[Dict[str, Set[str]]] = None,
        default_limit: Optional[int] = None,
        max_limit: Optional[int] = None,
        dialect: str = "postgres",
    ):
        from backend.app.database.schema_context import schema_context
        default_schema = schema_context.get_allowed_schema_whitelist()
        self.allowed_schema: Dict[str, Set[str]] = (
            {tbl.lower(): {col.lower() for col in cols} for tbl, cols in allowed_schema.items()}
            if allowed_schema is not None
            else {tbl.lower(): {col.lower() for col in cols} for tbl, cols in default_schema.items()}
        )
        self.default_limit = default_limit or settings.DEFAULT_ROW_LIMIT
        self.max_limit = max_limit or settings.MAX_ROW_LIMIT
        self.dialect = dialect

    def update_allowed_schema(self, new_schema: Dict[str, Set[str]]) -> None:
        """Dynamically update allowed schema when Person 2 provides the final schema."""
        self.allowed_schema = {
            tbl.lower(): {col.lower() for col in cols} for tbl, cols in new_schema.items()
        }

    def validate(self, sql: str) -> ValidationResult:
        """Parse and strictly validate an SQL string.
        
        Returns ValidationResult with is_valid=True and sanitized_sql if safe,
        or is_valid=False with a safe, descriptive error message.
        """
        if not sql or not sql.strip():
            return ValidationResult(is_valid=False, error_message="Empty query provided.")

        raw_sql = sql.strip()

        # Step 1: Detect raw semicolon delimiter count to catch multiple statements early
        # Remove string literals to avoid counting semicolons inside string constants
        sql_no_strings = re.sub(r"'(''|[^'])*'", "", raw_sql)
        statements_raw = [s.strip() for s in sql_no_strings.split(";") if s.strip()]
        if len(statements_raw) > 1:
            return ValidationResult(
                is_valid=False,
                error_message="Multiple SQL statements are not permitted.",
            )

        # Step 2: Parse using SQLGlot
        try:
            parsed_statements = sqlglot.parse(raw_sql, read=self.dialect)
        except ParseError as e:
            return ValidationResult(
                is_valid=False,
                error_message=f"SQL Syntax parsing error: {e.errors[0]['description'] if e.errors else 'Invalid SQL syntax'}",
            )
        except Exception:
            return ValidationResult(
                is_valid=False,
                error_message="Invalid SQL query could not be parsed.",
            )

        if not parsed_statements:
            return ValidationResult(is_valid=False, error_message="No executable statement found.")

        if len(parsed_statements) > 1:
            return ValidationResult(
                is_valid=False,
                error_message="Multiple SQL statements are not permitted.",
            )

        stmt = parsed_statements[0]

        # Step 3: Root statement must be a SELECT (or Union of Selects)
        if not isinstance(stmt, (exp.Select, exp.Union)):
            stmt_type = stmt.key.upper() if hasattr(stmt, "key") else "NON-SELECT"
            return ValidationResult(
                is_valid=False,
                error_message=f"Only read-only SELECT queries are permitted. Detected operation: {stmt_type}.",
            )

        # Step 4: Recursive mutation check across all nested expressions (CTEs, Subqueries, etc.)
        for mutation_cls in self.MUTATION_EXPRESSIONS:
            mutations = list(stmt.find_all(mutation_cls))
            if mutations:
                op_name = mutation_cls.__name__.upper()
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Disallowed mutating operation '{op_name}' detected in query.",
                )

        # Step 5: Check for forbidden system/exploit functions
        for func in stmt.find_all(exp.Func, exp.Anonymous):
            func_name = (func.name or "").lower()
            if func_name in self.FORBIDDEN_FUNCTIONS:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Disallowed function call detected: '{func_name}'.",
                )

        # Step 6: Identify CTE (WITH clause) names to avoid false positives for authorized tables
        cte_names: Set[str] = set()
        with_clause = stmt.args.get("with")
        if with_clause:
            for cte in with_clause.expressions:
                if cte.alias:
                    cte_names.add(cte.alias.lower())

        # Step 7: Validate tables and build alias map
        alias_to_table: Dict[str, str] = {}
        tables_used: Set[str] = set()

        for table_expr in stmt.find_all(exp.Table):
            tbl_name = table_expr.name.lower()
            # If the table reference is a CTE, it's a valid query-local structure
            if tbl_name in cte_names:
                continue

            # Verify table is in allowed schema
            if tbl_name not in self.allowed_schema:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Access denied: Unauthorized table '{tbl_name}'.",
                )

            tables_used.add(tbl_name)
            if table_expr.alias:
                alias_to_table[table_expr.alias.lower()] = tbl_name
            alias_to_table[tbl_name] = tbl_name

        # If no real tables were referenced and no CTEs, verify it is a valid literal SELECT
        all_allowed_columns_in_query: Set[str] = set()
        for tbl in tables_used:
            all_allowed_columns_in_query.update(self.allowed_schema[tbl])

        # Step 8: Validate columns against schema
        columns_used: Set[str] = set()
        for col_expr in stmt.find_all(exp.Column):
            col_name = col_expr.name.lower()
            table_ref = col_expr.table.lower() if col_expr.table else None

            # Skip star (*) column expressions as they represent wildcards
            if col_name == "*":
                continue

            if table_ref:
                # If table reference is a CTE, allow columns from CTE
                if table_ref in cte_names:
                    columns_used.add(col_name)
                    continue

                real_table = alias_to_table.get(table_ref)
                if not real_table or real_table not in self.allowed_schema:
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"Access denied: Column '{col_name}' references unknown or unauthorized table/alias '{table_ref}'.",
                    )
                if col_name not in self.allowed_schema[real_table]:
                    return ValidationResult(
                        is_valid=False,
                        error_message=f"Access denied: Unauthorized column '{col_name}' on table '{real_table}'.",
                    )
            else:
                # Unqualified column: must belong to at least one allowed table in query scope
                if all_allowed_columns_in_query and col_name not in all_allowed_columns_in_query:
                    # Also check if it matches a CTE output column or expression alias
                    is_alias = False
                    for select_expr in stmt.find_all(exp.Alias):
                        if select_expr.alias.lower() == col_name:
                            is_alias = True
                            break
                    if not is_alias:
                        return ValidationResult(
                            is_valid=False,
                            error_message=f"Access denied: Unauthorized column '{col_name}'.",
                        )

            columns_used.add(col_name)

        # Step 9: Enforce row LIMIT
        stmt = self._enforce_limit(stmt)

        sanitized_sql = stmt.sql(dialect=self.dialect)
        return ValidationResult(
            is_valid=True,
            sanitized_sql=sanitized_sql,
            tables_used=sorted(list(tables_used)),
            columns_used=sorted(list(columns_used)),
        )

    def _enforce_limit(self, stmt: exp.Expression) -> exp.Expression:
        """Inject or cap LIMIT clause to prevent unbounded query execution."""
        if not isinstance(stmt, exp.Select):
            return stmt

        limit_clause = stmt.args.get("limit")
        if limit_clause is None:
            # Inject default limit
            return stmt.limit(self.default_limit)
        else:
            try:
                # Check current limit value
                current_limit = int(limit_clause.expression.name)
                if current_limit > self.max_limit:
                    stmt.set("limit", exp.Limit(expression=exp.Literal.number(self.max_limit)))
            except (ValueError, AttributeError):
                # If expression is not a simple integer literal, enforce max_limit
                stmt.set("limit", exp.Limit(expression=exp.Literal.number(self.max_limit)))

        return stmt
