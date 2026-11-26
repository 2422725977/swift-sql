"""Unified ChatML prompts and strict JSON output formatting for SwiftSQL.

Supports three unified modes within a single lightweight model:
1. Generation (with Auto-Think: empty plan for simple queries, concise plan for complex queries)
2. Self-Repair (given broken SQL + DB/syntax error -> fixed SQL)
3. Refusal / Abstention (answerable=false when required schema columns are missing)
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

SYSTEM_PROMPT = (
    "You are SwiftSQL, a fast and accurate multi-dialect Text-to-SQL engine.\n"
    "Rules:\n"
    "1. Respond ONLY with a single valid JSON object. No markdown fences or extra text.\n"
    "2. Follow the requested SQL dialect strictly (postgresql, mysql, or sqlite) and output read-only SELECT queries only.\n"
    "3. Auto-Think: leave \"plan\" empty (\"\") for simple single-table queries; for multi-table JOINs, subqueries, CTEs, or window functions, write one concise sentence in \"plan\" before \"sql\".\n"
    "4. Never invent tables or columns. If the schema lacks required information to answer the question, set \"answerable\": false, \"sql\": \"\", and list missing fields in \"missing\"."
)


def build_generation_user_prompt(
    schema: str,
    question: str,
    dialect: str = "postgresql",
    mode: str = "auto",
) -> str:
    """Build user prompt for Text-to-SQL generation.

    mode: "auto" (Auto-Think), "fast" (force empty plan), or "think" (force concise plan).
    """
    return (
        f"Task: generate_sql\n"
        f"Dialect: {dialect}\n"
        f"Mode: {mode}\n"
        f"Schema:\n{schema.strip()}\n\n"
        f"Question:\n{question.strip()}"
    )


def build_repair_user_prompt(
    schema: str,
    question: str,
    broken_sql: str,
    error_message: str,
    dialect: str = "postgresql",
) -> str:
    """Build user prompt for 1-shot SQL self-repair."""
    return (
        f"Task: repair_sql\n"
        f"Dialect: {dialect}\n"
        f"Schema:\n{schema.strip()}\n\n"
        f"Question:\n{question.strip()}\n\n"
        f"Failed SQL:\n{broken_sql.strip()}\n\n"
        f"Error:\n{error_message.strip()}"
    )


def format_assistant_json(
    *,
    answerable: bool,
    dialect: str,
    sql: str = "",
    plan: str = "",
    tables: Optional[List[str]] = None,
    missing: Optional[List[str]] = None,
    note: str = "",
) -> str:
    """Serialize assistant response into compact, deterministic JSON."""
    payload: Dict[str, Any] = {
        "answerable": answerable,
        "plan": plan.strip() if plan else "",
        "dialect": dialect,
        "sql": sql.strip() if sql else "",
        "tables": tables or [],
    }
    if not answerable:
        payload["missing"] = missing or []
        payload["note"] = note.strip() or "Insufficient schema columns to answer the question."
    return json.dumps(payload, ensure_ascii=False)


def build_generation_messages(
    schema: str,
    question: str,
    dialect: str = "postgresql",
    mode: str = "auto",
    assistant_json: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Build ChatML message list for generation."""
    msgs = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_generation_user_prompt(
                schema=schema, question=question, dialect=dialect, mode=mode
            ),
        },
    ]
    if assistant_json is not None:
        msgs.append({"role": "assistant", "content": assistant_json})
    return msgs


def build_repair_messages(
    schema: str,
    question: str,
    broken_sql: str,
    error_message: str,
    dialect: str = "postgresql",
    assistant_json: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Build ChatML message list for SQL error repair."""
    msgs = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": build_repair_user_prompt(
                schema=schema,
                question=question,
                broken_sql=broken_sql,
                error_message=error_message,
                dialect=dialect,
            ),
        },
    ]
    if assistant_json is not None:
        msgs.append({"role": "assistant", "content": assistant_json})
    return msgs


def parse_model_response(raw_text: str, default_dialect: str = "postgresql") -> Dict[str, Any]:
    """Robustly parse JSON output from the model (with fallback extraction)."""
    text = (raw_text or "").strip()

    # Strip accidental markdown code fences if a base model emits them
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    # Try direct JSON parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return {
                "answerable": bool(obj.get("answerable", True)),
                "plan": str(obj.get("plan", "")),
                "dialect": str(obj.get("dialect", default_dialect)),
                "sql": str(obj.get("sql", "")).strip(),
                "tables": list(obj.get("tables", [])) if isinstance(obj.get("tables"), list) else [],
                "missing": list(obj.get("missing", [])) if isinstance(obj.get("missing"), list) else [],
                "note": str(obj.get("note", "")),
                "json_valid": True,
            }
    except Exception:
        pass

    # Fallback: try extracting first JSON object substring
    brace_match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if brace_match:
        try:
            obj = json.loads(brace_match.group(0))
            if isinstance(obj, dict):
                return {
                    "answerable": bool(obj.get("answerable", True)),
                    "plan": str(obj.get("plan", "")),
                    "dialect": str(obj.get("dialect", default_dialect)),
                    "sql": str(obj.get("sql", "")).strip(),
                    "tables": list(obj.get("tables", [])) if isinstance(obj.get("tables"), list) else [],
                    "missing": list(obj.get("missing", [])) if isinstance(obj.get("missing"), list) else [],
                    "note": str(obj.get("note", "")),
                    "json_valid": True,
                }
        except Exception:
            pass

    # Fallback for raw SQL output (e.g. when benchmarking an un-finetuned base model)
    sql_block = re.search(r"```sql\s*(.*?)\s*```", raw_text or "", flags=re.DOTALL | re.IGNORECASE)
    sql_guess = sql_block.group(1).strip() if sql_block else text
    return {
        "answerable": bool(sql_guess),
        "plan": "",
        "dialect": default_dialect,
        "sql": sql_guess,
        "tables": [],
        "missing": [],
        "note": "Fallback non-JSON response parsed.",
        "json_valid": False,
    }
