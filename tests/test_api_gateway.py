"""Unit tests for the FastAPI SwiftSQL gateway, read-only guardrail, and auto-repair loop."""

from fastapi.testclient import TestClient

from serve.api_gateway import create_app
from swiftsql.prompts import format_assistant_json


def test_gateway_auth_and_auto_repair():
    calls = []

    async def fake_llm(messages):
        calls.append(messages)
        # First call intentionally returns broken SQL syntax; second call returns repaired valid SQL
        if len(calls) == 1:
            return format_assistant_json(
                answerable=True,
                dialect="postgresql",
                sql="SELECT name FORM users WHERE id = 1",
                plan="",
                tables=["users"],
            )
        return format_assistant_json(
            answerable=True,
            dialect="postgresql",
            sql="SELECT name FROM users WHERE id = 1",
            plan="Fix typo FORM -> FROM.",
            tables=["users"],
        )

    app = create_app(llm_caller=fake_llm, api_keys=["secret-token"])
    client = TestClient(app)

    # Reject missing API key
    r_unauth = client.post(
        "/v1/text2sql",
        json={"schema": "CREATE TABLE users (id INT, name TEXT);", "question": "Get user 1"},
    )
    assert r_unauth.status_code == 401

    # Valid API key triggers automatic 1-shot SQL self-repair
    r_ok = client.post(
        "/v1/text2sql",
        headers={"Authorization": "Bearer secret-token"},
        json={
            "schema": "CREATE TABLE users (id INT, name TEXT);",
            "question": "Get user 1",
            "dialect": "postgresql",
        },
    )
    assert r_ok.status_code == 200
    body = r_ok.json()
    assert body["answerable"] is True
    assert body["repaired"] is True
    assert body["syntax_valid"] is True
    assert "FROM users" in body["sql"]
    assert len(calls) == 2


def test_gateway_blocks_destructive_sql():
    async def evil_llm(_messages):
        return format_assistant_json(
            answerable=True,
            dialect="postgresql",
            sql="DROP TABLE users;",
            plan="",
            tables=["users"],
        )

    app = create_app(llm_caller=evil_llm, api_keys=[])
    client = TestClient(app)
    resp = client.post(
        "/v1/text2sql",
        json={
            "schema": "CREATE TABLE users (id INT, name TEXT);",
            "question": "Delete everything",
            "allow_repair": False,
        },
    )
    assert resp.status_code == 422


def test_gateway_refusal_passthrough():
    async def refusal_llm(_messages):
        return format_assistant_json(
            answerable=False,
            dialect="mysql",
            sql="",
            missing=["phone"],
            note="Missing phone column.",
        )

    app = create_app(llm_caller=refusal_llm, api_keys=[])
    client = TestClient(app)
    resp = client.post(
        "/v1/text2sql",
        json={
            "schema": "CREATE TABLE users (id INT, name TEXT);",
            "question": "Find Alice's phone number",
            "dialect": "mysql",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answerable"] is False
    assert body["sql"] == ""
    assert body["missing"] == ["phone"]
