"""Multi-source public dataset builder with Auto-Think, multi-dialect, repair, and refusal synthesis."""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from swiftsql.dialect import (
    analyze_complexity,
    drop_column_from_ddl,
    extract_ddl_only,
    extract_referenced_columns,
    extract_schema_tables_and_columns,
    transpile_sql,
    validate_sql,
)
from swiftsql.prompts import (
    build_generation_messages,
    build_repair_messages,
    format_assistant_json,
)


@dataclass
class RawExample:
    schema: str
    question: str
    sql: str
    source: str
    explanation: str = ""
    executable_context: str = ""  # Optional CREATE TABLE + INSERT INTO for SQLite sandbox eval
    language: str = "en"


def compress_plan(explanation: str, tables: List[str], sql: str) -> str:
    """Create a concise 1-sentence Auto-Think plan (<= 160 chars) for complex queries."""
    if explanation and explanation.strip():
        first_sentence = re.split(r"(?<=[.!?。！？])\s+", explanation.strip())[0]
        if len(first_sentence) <= 160:
            return first_sentence
        return first_sentence[:157].rstrip() + "..."
    tbl_str = ", ".join(tables) if tables else "schema tables"
    hints = []
    upper = sql.upper()
    if "JOIN" in upper:
        hints.append("join tables")
    if "GROUP BY" in upper:
        hints.append("group and aggregate")
    if "HAVING" in upper:
        hints.append("filter aggregates")
    if "OVER(" in upper or "OVER (" in upper:
        hints.append("apply window function")
    if "WITH " in upper:
        hints.append("compute CTE")
    action = ", ".join(hints) if hints else "query and filter"
    return f"Use {tbl_str} to {action} according to the question."


def pick_dialect(rng: random.Random, dialect_weights: Dict[str, float]) -> str:
    dialects = list(dialect_weights.keys())
    weights = [dialect_weights[d] for d in dialects]
    return rng.choices(dialects, weights=weights, k=1)[0]


def synthesize_broken_sql(
    valid_sql: str,
    dialect: str,
    rng: random.Random,
) -> Optional[Tuple[str, str]]:
    """Introduce realistic, deterministic SQL bugs paired with realistic DB error messages."""
    strategies = ["bad_column", "missing_from", "wrong_dialect_func", "unmatched_paren"]
    rng.shuffle(strategies)

    cols = sorted(extract_referenced_columns(valid_sql, dialect=dialect))
    for strat in strategies:
        if strat == "bad_column" and cols:
            col = rng.choice(cols)
            bad_col = f"{col}_val"
            broken = re.sub(rf"\b{re.escape(col)}\b", bad_col, valid_sql, count=1, flags=re.IGNORECASE)
            if broken != valid_sql:
                err = (
                    f'column "{bad_col}" does not exist'
                    if dialect == "postgresql"
                    else f"Unknown column '{bad_col}' in 'field list'"
                    if dialect == "mysql"
                    else f"no such column: {bad_col}"
                )
                return broken, err

        if strat == "missing_from" and re.search(r"\bFROM\b", valid_sql, flags=re.IGNORECASE):
            broken = re.sub(r"\bFROM\b", "FORM", valid_sql, count=1, flags=re.IGNORECASE)
            if broken != valid_sql:
                return broken, f'syntax error at or near "FORM" ({dialect})'

        if strat == "wrong_dialect_func" and re.search(r"\bLIMIT\s+\d+", valid_sql, flags=re.IGNORECASE):
            if dialect == "postgresql":
                broken = re.sub(r"\bLIMIT\s+(\d+)", r"LIMIT 0, \1", valid_sql, count=1, flags=re.IGNORECASE)
                if broken != valid_sql:
                    return broken, 'syntax error at or near "," (PostgreSQL uses LIMIT n OFFSET m, not MySQL LIMIT m, n)'

        if strat == "unmatched_paren" and "(" in valid_sql and ")" in valid_sql:
            idx = valid_sql.rfind(")")
            broken = valid_sql[:idx] + valid_sql[idx + 1 :]
            return broken, f"syntax error: unmatched '(' near end of query ({dialect})"

    return None


def synthesize_refusal_record(
    example: RawExample,
    dialect: str,
    rng: random.Random,
) -> Optional[Dict[str, Any]]:
    """Drop a column referenced by the gold SQL from the DDL to build an unanswerable refusal sample."""
    ddl_only = extract_ddl_only(example.schema)
    schema_cols = extract_schema_tables_and_columns(ddl_only)
    if not schema_cols:
        return None

    ref_cols = extract_referenced_columns(example.sql, dialect="sqlite")
    # Pick a referenced column that exists in a table with at least 2 columns
    candidates = []
    for table, cols in schema_cols.items():
        if len(cols) < 2:
            continue
        for c in cols:
            if c.lower() in ref_cols and not c.lower().endswith("id"):
                candidates.append(c)

    if not candidates:
        return None

    drop_col = rng.choice(candidates)
    mutated_ddl = drop_column_from_ddl(ddl_only, drop_col)
    if not mutated_ddl:
        return None

    note = (
        f"提供的表结构中缺少回答该问题所需的字段：{drop_col}。"
        if example.language == "zh"
        else f"The provided schema does not contain the required column '{drop_col}' to answer this question."
    )
    assistant_json = format_assistant_json(
        answerable=False,
        dialect=dialect,
        sql="",
        plan="",
        tables=[],
        missing=[drop_col],
        note=note,
    )
    return {
        "task_type": "refusal",
        "source": example.source,
        "dialect": dialect,
        "complexity": "refusal",
        "language": example.language,
        "messages": build_generation_messages(
            schema=mutated_ddl,
            question=example.question,
            dialect=dialect,
            mode="auto",
            assistant_json=assistant_json,
        ),
        "meta": {
            "schema": mutated_ddl,
            "question": example.question,
            "gold_sql": "",
            "answerable": False,
            "missing": [drop_col],
            "dialect": dialect,
            "executable_context": "",
        },
    }


def build_sft_records(
    raw_examples: Sequence[RawExample],
    *,
    dialect_weights: Optional[Dict[str, float]] = None,
    repair_ratio: float = 0.20,
    refusal_ratio: float = 0.10,
    max_schema_chars: int = 4000,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """Transform raw examples into SwiftSQL's unified multi-task SFT dataset."""
    rng = random.Random(seed)
    weights = dialect_weights or {"postgresql": 0.40, "mysql": 0.35, "sqlite": 0.25}
    records: List[Dict[str, Any]] = []
    valid_pool: List[Tuple[RawExample, str, str, str, bool, List[str]]] = []

    for ex in raw_examples:
        ddl_clean = extract_ddl_only(ex.schema)
        if not ddl_clean or len(ddl_clean) > max_schema_chars:
            continue
        if not ex.question.strip() or not ex.sql.strip():
            continue

        # Validate read-only SQLite/generic source SQL
        src_check = validate_sql(ex.sql, dialect="sqlite", require_read_only=True)
        if not src_check.valid:
            continue

        target_dialect = pick_dialect(rng, weights)
        transpiled = transpile_sql(ex.sql, source_dialect="sqlite", target_dialect=target_dialect)
        if not transpiled:
            target_dialect = "sqlite"
            transpiled = src_check.normalized_sql

        level, needs_plan, tables = analyze_complexity(transpiled, dialect=target_dialect)
        plan = compress_plan(ex.explanation, tables, transpiled) if needs_plan else ""

        assistant_json = format_assistant_json(
            answerable=True,
            dialect=target_dialect,
            sql=transpiled,
            plan=plan,
            tables=tables,
        )
        records.append(
            {
                "task_type": "generate",
                "source": ex.source,
                "dialect": target_dialect,
                "complexity": level,
                "language": ex.language,
                "messages": build_generation_messages(
                    schema=ddl_clean,
                    question=ex.question,
                    dialect=target_dialect,
                    mode="auto",
                    assistant_json=assistant_json,
                ),
                "meta": {
                    "schema": ddl_clean,
                    "question": ex.question,
                    "gold_sql": transpiled,
                    "gold_sqlite_sql": src_check.normalized_sql,
                    "answerable": True,
                    "dialect": target_dialect,
                    "complexity": level,
                    "executable_context": ex.executable_context,
                },
            }
        )
        valid_pool.append((ex, ddl_clean, target_dialect, transpiled, needs_plan, tables))

    # Synthesize SQL Repair samples
    rng.shuffle(valid_pool)
    repair_target = int(len(valid_pool) * repair_ratio)
    repair_added = 0
    for ex, ddl_clean, target_dialect, transpiled, _needs_plan, tables in valid_pool:
        if repair_added >= repair_target:
            break
        broken = synthesize_broken_sql(transpiled, dialect=target_dialect, rng=rng)
        if not broken:
            continue
        broken_sql, err_msg = broken
        repair_plan = f"Fix the {target_dialect} error ({err_msg[:70]}) using valid schema identifiers."
        assistant_json = format_assistant_json(
            answerable=True,
            dialect=target_dialect,
            sql=transpiled,
            plan=repair_plan,
            tables=tables,
        )
        records.append(
            {
                "task_type": "repair",
                "source": ex.source,
                "dialect": target_dialect,
                "complexity": "repair",
                "language": ex.language,
                "messages": build_repair_messages(
                    schema=ddl_clean,
                    question=ex.question,
                    broken_sql=broken_sql,
                    error_message=err_msg,
                    dialect=target_dialect,
                    assistant_json=assistant_json,
                ),
                "meta": {
                    "schema": ddl_clean,
                    "question": ex.question,
                    "broken_sql": broken_sql,
                    "error_message": err_msg,
                    "gold_sql": transpiled,
                    "answerable": True,
                    "dialect": target_dialect,
                    "executable_context": ex.executable_context,
                },
            }
        )
        repair_added += 1

    # Synthesize Unanswerable Refusal samples
    refusal_target = int(len(valid_pool) * refusal_ratio)
    refusal_added = 0
    for ex, _ddl_clean, target_dialect, _transpiled, _needs_plan, _tables in reversed(valid_pool):
        if refusal_added >= refusal_target:
            break
        rec = synthesize_refusal_record(ex, dialect=target_dialect, rng=rng)
        if rec:
            records.append(rec)
            refusal_added += 1

    rng.shuffle(records)
    return records


def load_public_hf_datasets(
    *,
    gretel_train_samples: int = 4500,
    sqale_train_samples: int = 2000,
    chinese_train_samples: int = 2000,
    eval_samples: int = 400,
    seed: int = 42,
) -> Tuple[List[RawExample], List[RawExample]]:
    """Download and stratify verified open Hugging Face Text-to-SQL datasets.

    Datasets used (all open without HF token required):
    - gretelai/synthetic_text_to_sql (train + test, includes CREATE + INSERT for real execution eval!)
    - trl-lab/SQaLe-text-to-SQL-dataset (multi-table enterprise schemas)
    - jtjt520j/CSpider_and_DUSQL_sql_create_context (Chinese Text-to-SQL)
    """
    from datasets import load_dataset

    rng = random.Random(seed)
    train_raw: List[RawExample] = []
    eval_raw: List[RawExample] = []

    # 1. Gretel Synthetic Text-to-SQL (train + test)
    if gretel_train_samples > 0 or eval_samples > 0:
        gretel = load_dataset("gretelai/synthetic_text_to_sql")
        if gretel_train_samples > 0:
            rows = list(gretel["train"])
            rng.shuffle(rows)
            # Stratified pick: prioritize multi-join/subquery/window/aggregation diversity
            complex_rows = [
                r for r in rows if str(r.get("sql_complexity", "")).lower() not in ("basic sql", "single join")
            ]
            simple_rows = [
                r for r in rows if str(r.get("sql_complexity", "")).lower() in ("basic sql", "single join")
            ]
            n_complex = min(len(complex_rows), int(gretel_train_samples * 0.55))
            n_simple = min(len(simple_rows), gretel_train_samples - n_complex)
            picked = complex_rows[:n_complex] + simple_rows[:n_simple]
            for r in picked:
                train_raw.append(
                    RawExample(
                        schema=r["sql_context"],
                        question=r["sql_prompt"],
                        sql=r["sql"],
                        source="gretel",
                        explanation=r.get("sql_explanation", "") or "",
                        executable_context=r["sql_context"],
                        language="en",
                    )
                )
        if eval_samples > 0:
            test_rows = list(gretel["test"])
            rng.shuffle(test_rows)
            for r in test_rows[:eval_samples]:
                eval_raw.append(
                    RawExample(
                        schema=r["sql_context"],
                        question=r["sql_prompt"],
                        sql=r["sql"],
                        source="gretel_test",
                        explanation=r.get("sql_explanation", "") or "",
                        executable_context=r["sql_context"],
                        language="en",
                    )
                )

    # 2. SQaLe (streaming so Colab never downloads all 500k rows unnecessarily)
    if sqale_train_samples > 0:
        sqale_stream = load_dataset("trl-lab/SQaLe-text-to-SQL-dataset", split="train", streaming=True)
        count = 0
        for r in sqale_stream:
            schema = r.get("schema", "")
            if not schema or len(schema) > 4000:
                continue
            train_raw.append(
                RawExample(
                    schema=schema,
                    question=r.get("question", ""),
                    sql=r.get("query", ""),
                    source="sqale",
                    language="en",
                )
            )
            count += 1
            if count >= sqale_train_samples:
                break

    # 3. Chinese CSpider + DuSQL
    if chinese_train_samples > 0:
        zh_ds = load_dataset("jtjt520j/CSpider_and_DUSQL_sql_create_context", split="train")
        zh_rows = list(zh_ds)
        rng.shuffle(zh_rows)
        # Hold out 100 Chinese samples for bilingual eval if eval_samples > 0
        zh_eval_count = min(100, max(0, eval_samples // 4))
        for r in zh_rows[:zh_eval_count]:
            eval_raw.append(
                RawExample(
                    schema=r["context"],
                    question=r["question"],
                    sql=r["answer"],
                    source="zh_dusql_eval",
                    language="zh",
                )
            )
        for r in zh_rows[zh_eval_count : zh_eval_count + chinese_train_samples]:
            train_raw.append(
                RawExample(
                    schema=r["context"],
                    question=r["question"],
                    sql=r["answer"],
                    source="zh_dusql",
                    language="zh",
                )
            )

    return train_raw, eval_raw


def save_jsonl(records: Iterable[Dict[str, Any]], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            count += 1
    return count


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
