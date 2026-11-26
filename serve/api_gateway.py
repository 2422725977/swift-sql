"""Lightweight FastAPI Text-to-SQL gateway for Apple Silicon Mac mini (16GB).

Features:
- Connects to local Ollama (`http://localhost:11434/v1`) or llama.cpp (`http://localhost:8080/v1`) or MLX server
- Bearer API key authentication + per-key rate limiting + concurrency semaphore
- Deterministic `sqlglot` read-only safety guardrail & dialect syntax check (< 2ms)
- Automatic 1-shot SQL self-repair using the exact same lightweight model when syntax check fails
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict, deque
from typing import Any, Callable, Coroutine, Deque, Dict, List, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from swiftsql.dialect import normalize_dialect, validate_sql
from swiftsql.prompts import (
    build_generation_messages,
    build_repair_messages,
    parse_model_response,
)


class Text2SQLRequest(BaseModel):
    schema_sql: str = Field(..., alias="schema", description="CREATE TABLE DDL statements")
    question: str = Field(..., description="Natural language question (Chinese or English)")
    dialect: str = Field("postgresql", description="Target dialect: postgresql | mysql | sqlite")
    mode: str = Field("auto", description="Auto-Think mode: auto | fast | think")
    allow_repair: bool = Field(True, description="Automatically run 1-shot self-repair on syntax errors")

    model_config = {"populate_by_name": True}


class Text2SQLResponse(BaseModel):
    answerable: bool
    dialect: str
    sql: str
    plan: str = ""
    tables: List[str] = Field(default_factory=list)
    missing: List[str] = Field(default_factory=list)
    note: str = ""
    repaired: bool = False
    syntax_valid: bool = True
    latency_ms: float = 0.0


LLMCallable = Callable[[List[Dict[str, str]]], Coroutine[Any, Any, str]]


class RateLimiter:
    def __init__(self, max_requests_per_minute: int = 60) -> None:
        self.limit = max_requests_per_minute
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and (now - bucket[0]) > 60.0:
            bucket.popleft()
        if len(bucket) >= self.limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Please slow down.")
        bucket.append(now)


def create_app(
    *,
    llm_caller: Optional[LLMCallable] = None,
    api_keys: Optional[List[str]] = None,
    max_concurrency: int = 4,
    rpm_limit: int = 60,
) -> FastAPI:
    backend_url = os.getenv("SWIFTSQL_BACKEND_URL", "http://127.0.0.1:11434/v1/chat/completions")
    backend_model = os.getenv("SWIFTSQL_MODEL_NAME", "swiftsql-3b")
    env_keys = os.getenv("SWIFTSQL_API_KEYS", "")
    valid_keys = set(api_keys if api_keys is not None else [k.strip() for k in env_keys.split(",") if k.strip()])

    semaphore = asyncio.Semaphore(max_concurrency)
    limiter = RateLimiter(max_requests_per_minute=rpm_limit)

    async def default_llm_caller(messages: List[Dict[str, str]]) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                backend_url,
                json={
                    "model": backend_model,
                    "messages": messages,
                    "temperature": 0.0,
                    "max_tokens": 512,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    call_llm = llm_caller or default_llm_caller
    app = FastAPI(title="SwiftSQL API Gateway", version="0.1.0")

    def verify_api_key(authorization: Optional[str] = Header(default=None)) -> str:
        if not valid_keys:
            return "anonymous"
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer API key.")
        token = authorization.removeprefix("Bearer ").strip()
        if token not in valid_keys:
            raise HTTPException(status_code=403, detail="Invalid API key.")
        limiter.check(token)
        return token

    @app.get("/health")
    async def health() -> Dict[str, str]:
        return {"status": "ok", "model": backend_model}

    @app.post("/v1/text2sql", response_model=Text2SQLResponse)
    async def text2sql(
        req: Text2SQLRequest,
        _api_key: str = Depends(verify_api_key),
    ) -> Text2SQLResponse:
        t0 = time.perf_counter()
        try:
            dialect = normalize_dialect(req.dialect)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        async with semaphore:
            gen_msgs = build_generation_messages(
                schema=req.schema_sql,
                question=req.question,
                dialect=dialect,
                mode=req.mode,
            )
            raw = await call_llm(gen_msgs)
            parsed = parse_model_response(raw, default_dialect=dialect)

            # Unanswerable / refusal path
            if not parsed["answerable"]:
                return Text2SQLResponse(
                    answerable=False,
                    dialect=dialect,
                    sql="",
                    plan=parsed["plan"],
                    tables=[],
                    missing=parsed["missing"],
                    note=parsed["note"] or "Schema lacks required fields.",
                    repaired=False,
                    syntax_valid=True,
                    latency_ms=round((time.perf_counter() - t0) * 1000.0, 1),
                )

            val = validate_sql(parsed["sql"], dialect=dialect, require_read_only=True)
            repaired = False

            # Automatic 1-shot SQL Repair when syntax or read-only guardrail trips
            if (not val.valid) and req.allow_repair:
                repair_msgs = build_repair_messages(
                    schema=req.schema_sql,
                    question=req.question,
                    broken_sql=parsed["sql"],
                    error_message=val.error,
                    dialect=dialect,
                )
                raw_repaired = await call_llm(repair_msgs)
                parsed_repaired = parse_model_response(raw_repaired, default_dialect=dialect)
                if parsed_repaired["answerable"] and parsed_repaired["sql"]:
                    val_repaired = validate_sql(
                        parsed_repaired["sql"], dialect=dialect, require_read_only=True
                    )
                    if val_repaired.valid:
                        parsed = parsed_repaired
                        val = val_repaired
                        repaired = True

            if not val.read_only:
                raise HTTPException(
                    status_code=422,
                    detail="Blocked unsafe non-read-only SQL query.",
                )

            return Text2SQLResponse(
                answerable=True,
                dialect=dialect,
                sql=val.normalized_sql if val.valid else parsed["sql"],
                plan=parsed["plan"],
                tables=val.tables or parsed["tables"],
                missing=[],
                note="" if val.valid else val.error,
                repaired=repaired,
                syntax_valid=val.valid,
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 1),
            )

    return app


app = create_app()
