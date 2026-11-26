"""Unit tests for multi-dialect SQL parsing, transpilation, safety checks, and schema ops."""

import pytest

from swiftsql.dialect import (
    analyze_complexity,
    drop_column_from_ddl,
    extract_ddl_only,
    extract_schema_tables_and_columns,
    normalize_dialect,
    transpile_sql,
    validate_sql,
)


def test_normalize_dialect():
    assert normalize_dialect("pg") == "postgresql"
    assert normalize_dialect("PostgreSQL") == "postgresql"
    assert normalize_dialect("MySQL") == "mysql"
    assert normalize_dialect("sqlite") == "sqlite"
    with pytest.raises(ValueError):
        normalize_dialect("oracle")


def test_validate_sql_read_only_guardrail():
    ok = validate_sql("SELECT id, name FROM users WHERE active = 1 LIMIT 10", dialect="postgresql")
    assert ok.valid is True
    assert ok.read_only is True
    assert ok.tables == ["users"]

    for dangerous in [
        "DROP TABLE users;",
        "DELETE FROM users WHERE id = 1;",
        "UPDATE users SET role = 'admin';",
        "INSERT INTO users VALUES (1, 'a');",
        "SELECT 1; DROP TABLE users;",
    ]:
        res = validate_sql(dangerous, dialect="postgresql", require_read_only=True)
        assert res.valid is False
        assert res.read_only is False


def test_transpile_sql_across_dialects():
    sql = "SELECT id, name FROM users ORDER BY id DESC LIMIT 5"
    pg = transpile_sql(sql, source_dialect="sqlite", target_dialect="postgresql")
    my = transpile_sql(sql, source_dialect="sqlite", target_dialect="mysql")
    assert pg is not None and "LIMIT 5" in pg
    assert my is not None and "LIMIT 5" in my


def test_analyze_complexity_auto_think():
    lvl_simple, need_plan_simple, tables_simple = analyze_complexity(
        "SELECT name FROM users WHERE age > 30", dialect="postgresql"
    )
    assert lvl_simple == "simple"
    assert need_plan_simple is False
    assert tables_simple == ["users"]

    lvl_complex, need_plan_complex, tables_complex = analyze_complexity(
        "SELECT u.name, SUM(o.amount) FROM users u JOIN orders o ON u.id = o.user_id "
        "GROUP BY u.name HAVING SUM(o.amount) > 100",
        dialect="postgresql",
    )
    assert lvl_complex in ("medium", "complex")
    assert need_plan_complex is True
    assert tables_complex == ["orders", "users"]


def test_extract_ddl_and_drop_column_for_refusal():
    ctx = (
        "CREATE TABLE employees (emp_id INT, name TEXT, salary INT, dept TEXT);\n"
        "INSERT INTO employees VALUES (1, 'Alice', 9000, 'Eng');"
    )
    ddl = extract_ddl_only(ctx)
    assert "INSERT INTO" not in ddl
    assert "CREATE TABLE employees" in ddl

    cols = extract_schema_tables_and_columns(ddl)
    assert cols == {"employees": ["emp_id", "name", "salary", "dept"]}

    mutated = drop_column_from_ddl(ddl, "salary")
    assert mutated is not None
    assert "salary" not in mutated.lower()
    assert "dept" in mutated.lower()
