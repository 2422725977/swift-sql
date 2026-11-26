"""Unit tests for SQLite sandbox evaluation and Execution-Guided DPO pair builder."""

from swiftsql.data_pipeline import RawExample, build_sft_records
from swiftsql.dpo_builder import build_dpo_pair
from swiftsql.evaluation import evaluate_predictions, execute_sqlite_sandbox, results_match
from swiftsql.prompts import format_assistant_json


def test_sqlite_sandbox_execution_and_results_match():
    ctx = (
        "CREATE TABLE items (id INT, name TEXT, price REAL);"
        "INSERT INTO items VALUES (1, 'Pen', 2.5), (2, 'Book', 12.0);"
    )
    out = execute_sqlite_sandbox(ctx, "SELECT name, price FROM items WHERE price > 5")
    assert out.success is True
    assert out.rows == [("Book", 12.0)]
    assert results_match([("Book", 12.00001)], [("book", 12.0)], order_sensitive=False) is True

    blocked = execute_sqlite_sandbox(ctx, "DROP TABLE items;")
    assert blocked.success is False


def test_evaluate_predictions_metrics():
    ctx = (
        "CREATE TABLE sales (id INT, region TEXT, amount INT);"
        "INSERT INTO sales VALUES (1, 'East', 100), (2, 'East', 50), (3, 'West', 80);"
    )
    raw = [
        RawExample(
            schema=ctx,
            question="Total sales per region",
            sql="SELECT region, SUM(amount) FROM sales GROUP BY region",
            source="test",
            executable_context=ctx,
        )
    ]
    records = build_sft_records(raw, repair_ratio=0.0, refusal_ratio=1.0, seed=7)
    # Build perfect predictions directly from gold assistant messages
    preds = [r["messages"][2]["content"] for r in records]
    report = evaluate_predictions(records, preds, latencies_ms=[120.0] * len(records))
    assert report["json_valid_rate"] == 1.0
    assert report["syntax_valid_rate"] == 1.0
    assert report["execution_accuracy"] == 1.0
    assert report["refusal_f1"] == 1.0


def test_dpo_builder_prefers_correct_and_concise():
    ctx = (
        "CREATE TABLE users (id INT, name TEXT, age INT);"
        "INSERT INTO users VALUES (1, 'Alice', 31), (2, 'Bob', 22);"
    )
    raw = [
        RawExample(
            schema=ctx,
            question="Find names of users older than 25",
            sql="SELECT name FROM users WHERE age > 25",
            source="test",
            executable_context=ctx,
        )
    ]
    rec = build_sft_records(
        raw, dialect_weights={"sqlite": 1.0}, repair_ratio=0.0, refusal_ratio=0.0, seed=1
    )[0]

    good_concise = format_assistant_json(
        answerable=True,
        dialect="sqlite",
        sql="SELECT name FROM users WHERE age > 25",
        plan="",
        tables=["users"],
    )
    wrong_sql = format_assistant_json(
        answerable=True,
        dialect="sqlite",
        sql="SELECT name FROM users WHERE age < 25",
        plan="Verbose wrong plan explaining something incorrect for a long time.",
        tables=["users"],
    )
    pair = build_dpo_pair(rec, [good_concise, wrong_sql])
    assert pair is not None
    assert pair["chosen"][0]["content"] == good_concise
    assert pair["rejected"][0]["content"] == wrong_sql
    assert pair["meta"]["pair_source"] == "self_contrast"
