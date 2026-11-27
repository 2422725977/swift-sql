"""Unit tests for SwiftSQL multi-task dataset synthesis and JSON prompt parsing."""

import json

from swiftsql.data_pipeline import RawExample, build_sft_records
from swiftsql.prompts import parse_model_response


def _sample_raw_examples():
    return [
        RawExample(
            schema=(
                "CREATE TABLE customers (customer_id INT, name TEXT, city TEXT);\n"
                "INSERT INTO customers VALUES (1, 'Alice', 'Beijing'), (2, 'Bob', 'Shanghai');"
            ),
            question="List all customers in Beijing.",
            sql="SELECT name FROM customers WHERE city = 'Beijing'",
            source="unit",
            executable_context=(
                "CREATE TABLE customers (customer_id INT, name TEXT, city TEXT);\n"
                "INSERT INTO customers VALUES (1, 'Alice', 'Beijing'), (2, 'Bob', 'Shanghai');"
            ),
            language="en",
        ),
        RawExample(
            schema=(
                "CREATE TABLE users (user_id INT, name TEXT, country TEXT);\n"
                "CREATE TABLE orders (order_id INT, user_id INT, amount REAL, status TEXT);\n"
                "INSERT INTO users VALUES (1, 'Alice', 'CN');\n"
                "INSERT INTO orders VALUES (10, 1, 250.5, 'paid');"
            ),
            question="统计每个用户的已支付订单总金额",
            sql=(
                "SELECT u.name, SUM(o.amount) AS total_amount "
                "FROM users u JOIN orders o ON u.user_id = o.user_id "
                "WHERE o.status = 'paid' GROUP BY u.name"
            ),
            source="unit_zh",
            explanation="Join users and orders on user_id, filter paid orders, and sum amount per user.",
            executable_context=(
                "CREATE TABLE users (user_id INT, name TEXT, country TEXT);\n"
                "CREATE TABLE orders (order_id INT, user_id INT, amount REAL, status TEXT);\n"
                "INSERT INTO users VALUES (1, 'Alice', 'CN');\n"
                "INSERT INTO orders VALUES (10, 1, 250.5, 'paid');"
            ),
            language="zh",
        ),
    ] * 10


def test_build_sft_records_contains_generate_repair_refusal():
    records = build_sft_records(
        _sample_raw_examples(),
        repair_ratio=0.30,
        refusal_ratio=0.20,
        seed=42,
    )
    task_types = {r["task_type"] for r in records}
    assert {"generate", "repair", "refusal"}.issubset(task_types)

    for rec in records:
        msgs = rec["messages"]
        assert len(msgs) == 3
        assert [m["role"] for m in msgs] == ["system", "user", "assistant"]
        assistant_obj = json.loads(msgs[2]["content"])
        assert "answerable" in assistant_obj
        assert "sql" in assistant_obj
        if rec["task_type"] == "refusal":
            assert assistant_obj["answerable"] is False
            assert assistant_obj["sql"] == ""
            assert len(assistant_obj["missing"]) >= 1
        elif rec["task_type"] == "generate" and rec["complexity"] in ("simple", "medium"):
            # Fast Auto-Think: simple & single-JOIN queries must have empty plan
            assert assistant_obj["plan"] == ""
        elif rec["task_type"] == "generate" and rec["complexity"] == "complex":
            # Auto-Think: complex query must include an ultra-compact plan (<= 60 chars)
            assert 0 < len(assistant_obj["plan"]) <= 60


def test_sandbox_prefilter_drops_dirty_executable_rows():
    dirty_and_clean = [
        RawExample(
            schema="CREATE TABLE t (id INT, val TEXT); INSERT INTO t VALUES (1, 'a');",
            question="Broken gold SQL referencing missing column",
            sql="SELECT nonexistent_col FROM t",
            source="dirty",
            executable_context="CREATE TABLE t (id INT, val TEXT); INSERT INTO t VALUES (1, 'a');",
        ),
        RawExample(
            schema="CREATE TABLE t (id INT, val TEXT); INSERT INTO t VALUES (1, 'a');",
            question="Valid gold SQL",
            sql="SELECT val FROM t WHERE id = 1",
            source="clean",
            executable_context="CREATE TABLE t (id INT, val TEXT); INSERT INTO t VALUES (1, 'a');",
        ),
    ]
    records = build_sft_records(
        dirty_and_clean,
        dialect_weights={"sqlite": 1.0},
        repair_ratio=0.0,
        refusal_ratio=0.0,
        verify_executable=True,
        seed=42,
    )
    assert len(records) == 1
    assert records[0]["source"] == "clean"


def test_parse_model_response_robustness():
    clean = '{"answerable": true, "plan": "", "dialect": "postgresql", "sql": "SELECT 1", "tables": []}'
    p1 = parse_model_response(clean)
    assert p1["json_valid"] is True
    assert p1["sql"] == "SELECT 1"

    fenced = '```json\n{"answerable": false, "sql": "", "missing": ["email"]}\n```'
    p2 = parse_model_response(fenced)
    assert p2["json_valid"] is True
    assert p2["answerable"] is False
    assert p2["missing"] == ["email"]

    raw_sql = "```sql\nSELECT COUNT(*) FROM users;\n```"
    p3 = parse_model_response(raw_sql)
    assert p3["json_valid"] is False
    assert p3["sql"] == "SELECT COUNT(*) FROM users;"
