import pytest
from backend.app.agent.sql_validator import SQLValidator


@pytest.fixture
def validator():
    return SQLValidator()


def test_valid_select_query_passes(validator):
    sql = "SELECT building_id, consumption_kwh FROM energy_readings WHERE timestamp >= '2024-01-01'"
    res = validator.validate(sql)
    assert res.is_valid is True
    assert "LIMIT" in res.sanitized_sql.upper()
    assert "energy_readings" in res.tables_used


def test_valid_join_with_aliases_passes(validator):
    sql = """
        SELECT b.name, SUM(r.consumption_kwh) AS total_kwh
        FROM energy_readings r
        JOIN buildings b ON r.building_id = b.building_id
        WHERE r.timestamp >= '2024-01-01'
        GROUP BY b.name
        ORDER BY total_kwh DESC
        LIMIT 10
    """
    res = validator.validate(sql)
    assert res.is_valid is True
    assert set(res.tables_used) == {"buildings", "energy_readings"}


def test_reject_update_statement(validator):
    sql = "UPDATE energy_readings SET consumption_kwh = 0 WHERE id = 1"
    res = validator.validate(sql)
    assert res.is_valid is False
    assert "Only read-only SELECT queries are permitted" in res.error_message


def test_reject_delete_statement(validator):
    sql = "DELETE FROM energy_readings WHERE id = 1"
    res = validator.validate(sql)
    assert res.is_valid is False
    assert "Only read-only SELECT queries are permitted" in res.error_message


def test_reject_drop_table(validator):
    sql = "DROP TABLE buildings"
    res = validator.validate(sql)
    assert res.is_valid is False
    assert "Only read-only SELECT queries are permitted" in res.error_message


def test_reject_multiple_statements_with_semicolon(validator):
    sql = "SELECT * FROM buildings; DROP TABLE energy_readings;"
    res = validator.validate(sql)
    assert res.is_valid is False
    assert "Multiple SQL statements are not permitted" in res.error_message


def test_reject_unauthorized_table(validator):
    sql = "SELECT * FROM users"
    res = validator.validate(sql)
    assert res.is_valid is False
    assert "Unauthorized table 'users'" in res.error_message


def test_reject_unauthorized_column(validator):
    sql = "SELECT password_hash FROM buildings"
    res = validator.validate(sql)
    assert res.is_valid is False
    assert "Unauthorized column 'password_hash'" in res.error_message


def test_reject_cte_with_mutation(validator):
    sql = "WITH deleted AS (DELETE FROM energy_readings RETURNING *) SELECT * FROM deleted"
    res = validator.validate(sql)
    assert res.is_valid is False
    assert "Disallowed mutating operation" in res.error_message


def test_reject_forbidden_function_pg_sleep(validator):
    sql = "SELECT pg_sleep(10)"
    res = validator.validate(sql)
    assert res.is_valid is False
    assert "Disallowed function call detected: 'pg_sleep'" in res.error_message


def test_limit_capping(validator):
    # max_limit is 500 by default; query with 1000 should be capped to 500
    sql = "SELECT building_id FROM energy_readings LIMIT 1000"
    res = validator.validate(sql)
    assert res.is_valid is True
    assert "LIMIT 500" in res.sanitized_sql.upper()


def test_default_limit_injected_when_absent(validator):
    sql = "SELECT building_id FROM energy_readings"
    res = validator.validate(sql)
    assert res.is_valid is True
    assert f"LIMIT {validator.default_limit}" in res.sanitized_sql.upper()
