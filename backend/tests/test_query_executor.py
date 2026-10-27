import pytest
from backend.app.database.query_executor import SafeQueryExecutor


@pytest.fixture
def executor():
    return SafeQueryExecutor(max_rows=10)


def test_executor_successful_query(executor):
    sql = "SELECT building_id, name FROM buildings ORDER BY building_id ASC LIMIT 3"
    res = executor.execute_query(sql)
    assert res.success is True
    assert res.row_count == 3
    assert len(res.data) == 3
    assert "building_id" in res.data[0]
    assert "name" in res.data[0]


def test_executor_empty_results_handled(executor):
    sql = "SELECT * FROM energy_readings WHERE timestamp > '2099-01-01'"
    res = executor.execute_query(sql)
    assert res.success is True
    assert res.row_count == 0
    assert res.data == []
    assert res.error_message is None


def test_executor_row_limit_enforced(executor):
    # max_rows is 10
    sql = "SELECT * FROM energy_readings LIMIT 50"
    res = executor.execute_query(sql)
    assert res.success is True
    assert res.row_count == 10
    assert len(res.data) == 10


def test_executor_sanitizes_errors(executor):
    # Intentionally bad SQL syntax that bypasses or errors in execution
    bad_sql = "SELECT FROM non_existent_syntax_error"
    res = executor.execute_query(bad_sql)
    assert res.success is False
    assert res.error_message is not None
    # Verify no passwords or system traces leaked
    for sensitive in ["password", "token", "secret", "host"]:
        assert sensitive not in res.error_message.lower()


def test_sanitize_error_message_strips_credentials():
    executor = SafeQueryExecutor()
    simulated_err = "FATAL: password authentication failed for user 'postgres_admin' host 10.0.0.1"
    sanitized = executor._sanitize_error_message(simulated_err)
    assert "postgres_admin" not in sanitized
    assert "10.0.0.1" not in sanitized
    assert sanitized == "A database execution error occurred while processing the query."
