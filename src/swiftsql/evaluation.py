"""Execution-based SQLite sandbox evaluator and multi-metric benchmark for SwiftSQL."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from swiftsql.dialect import transpile_sql, validate_sql
from swiftsql.prompts import parse_model_response


@dataclass
class ExecutionOutcome:
    success: bool
    rows: List[Tuple[Any, ...]] = field(default_factory=list)
    error: str = ""
    elapsed_ms: float = 0.0


def execute_sqlite_sandbox(
    context_sql: str,
    query_sql: str,
    max_vm_steps: int = 500_000,
    max_rows: int = 2000,
) -> ExecutionOutcome:
    """Execute a read-only SQL query inside an isolated in-memory SQLite database.

    Protects against runaway cartesian products (via SQLite progress handler) and
    blocks non-read-only queries via sqlglot pre-validation.
    """
    t0 = time.perf_counter()
    check = validate_sql(query_sql, dialect="sqlite", require_read_only=True)
    if not check.valid:
        return ExecutionOutcome(
            success=False,
            error=check.error,
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )

    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(context_sql)

        steps = 0

        def _progress() -> int:
            nonlocal steps
            steps += 1000
            return 1 if steps > max_vm_steps else 0

        conn.set_progress_handler(_progress, 1000)
        cur = conn.execute(query_sql)
        rows = cur.fetchmany(max_rows)
        return ExecutionOutcome(
            success=True,
            rows=rows,
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )
    except Exception as exc:
        return ExecutionOutcome(
            success=False,
            error=str(exc),
            elapsed_ms=(time.perf_counter() - t0) * 1000.0,
        )
    finally:
        conn.close()


def _normalize_value(val: Any) -> Any:
    if isinstance(val, float):
        return round(val, 4)
    if isinstance(val, str):
        return val.strip().lower()
    return val


def results_match(
    pred_rows: Sequence[Tuple[Any, ...]],
    gold_rows: Sequence[Tuple[Any, ...]],
    order_sensitive: bool = False,
) -> bool:
    """Compare two query result sets with float rounding and optional order invariance."""
    norm_pred = [tuple(_normalize_value(v) for v in row) for row in pred_rows]
    norm_gold = [tuple(_normalize_value(v) for v in row) for row in gold_rows]
    if order_sensitive:
        return norm_pred == norm_gold
    return sorted(norm_pred, key=lambda r: tuple(str(x) for x in r)) == sorted(
        norm_gold, key=lambda r: tuple(str(x) for x in r)
    )


def evaluate_predictions(
    eval_records: Sequence[Dict[str, Any]],
    raw_predictions: Sequence[str],
    latencies_ms: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    """Compute comprehensive SwiftSQL metrics:
    - json_valid_rate: strict JSON compliance
    - syntax_valid_rate: target dialect sqlglot parse & read-only compliance
    - execution_accuracy (EX): exact result match on executable SQLite sandbox cases
    - refusal_accuracy / refusal_precision / refusal_recall: anti-hallucination quality
    - avg_output_chars & avg_latency_ms: speed & conciseness metrics
    """
    assert len(eval_records) == len(raw_predictions), "Records and predictions length mismatch."

    total = len(eval_records)
    json_ok = 0

    gen_total = 0
    syntax_ok = 0
    exec_total = 0
    exec_ok = 0

    refusal_tp = 0
    refusal_fp = 0
    refusal_fn = 0
    refusal_tn = 0

    total_chars = 0
    details: List[Dict[str, Any]] = []

    for idx, (rec, raw_pred) in enumerate(zip(eval_records, raw_predictions)):
        meta = rec.get("meta", {})
        dialect = meta.get("dialect", "postgresql")
        gold_answerable = bool(meta.get("answerable", True))
        parsed = parse_model_response(raw_pred, default_dialect=dialect)

        total_chars += len(raw_pred or "")
        if parsed["json_valid"]:
            json_ok += 1

        pred_answerable = bool(parsed["answerable"])
        item_detail: Dict[str, Any] = {
            "index": idx,
            "task_type": rec.get("task_type", "generate"),
            "dialect": dialect,
            "gold_answerable": gold_answerable,
            "pred_answerable": pred_answerable,
            "json_valid": parsed["json_valid"],
            "syntax_valid": None,
            "exec_match": None,
        }

        if not gold_answerable:
            if not pred_answerable:
                refusal_tp += 1
            else:
                refusal_fn += 1
            details.append(item_detail)
            continue

        # Gold IS answerable
        if not pred_answerable:
            refusal_fp += 1
            gen_total += 1
            item_detail["syntax_valid"] = False
            details.append(item_detail)
            continue

        refusal_tn += 1
        gen_total += 1

        val = validate_sql(parsed["sql"], dialect=dialect, require_read_only=True)
        item_detail["syntax_valid"] = val.valid
        if val.valid:
            syntax_ok += 1

        exec_ctx = meta.get("executable_context", "")
        gold_sqlite = meta.get("gold_sqlite_sql") or meta.get("gold_sql", "")
        if exec_ctx and gold_sqlite:
            gold_out = execute_sqlite_sandbox(exec_ctx, gold_sqlite)
            if gold_out.success:
                exec_total += 1
                # Transpile model SQL back to SQLite for sandbox execution comparison
                pred_sqlite = transpile_sql(parsed["sql"], source_dialect=dialect, target_dialect="sqlite")
                if pred_sqlite:
                    pred_out = execute_sqlite_sandbox(exec_ctx, pred_sqlite)
                    order_sensitive = "ORDER BY" in gold_sqlite.upper()
                    matched = pred_out.success and results_match(
                        pred_out.rows, gold_out.rows, order_sensitive=order_sensitive
                    )
                    item_detail["exec_match"] = matched
                    if matched:
                        exec_ok += 1
                else:
                    item_detail["exec_match"] = False

        details.append(item_detail)

    refusal_prec = refusal_tp / (refusal_tp + refusal_fp) if (refusal_tp + refusal_fp) else 1.0
    refusal_rec = refusal_tp / (refusal_tp + refusal_fn) if (refusal_tp + refusal_fn) else 1.0
    refusal_f1 = (
        2 * refusal_prec * refusal_rec / (refusal_prec + refusal_rec)
        if (refusal_prec + refusal_rec)
        else 0.0
    )

    return {
        "total_samples": total,
        "json_valid_rate": round(json_ok / total, 4) if total else 0.0,
        "syntax_valid_rate": round(syntax_ok / gen_total, 4) if gen_total else 0.0,
        "execution_accuracy": round(exec_ok / exec_total, 4) if exec_total else None,
        "executable_eval_count": exec_total,
        "refusal_precision": round(refusal_prec, 4),
        "refusal_recall": round(refusal_rec, 4),
        "refusal_f1": round(refusal_f1, 4),
        "avg_output_chars": round(total_chars / total, 1) if total else 0.0,
        "avg_latency_ms": round(sum(latencies_ms) / len(latencies_ms), 1) if latencies_ms else None,
        "details": details,
    }
