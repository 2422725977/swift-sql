"""Offline Execution-Guided DPO preference pair builder.

Inspired by Auto-ThinkSQL & execution-guided RL:
- Rewards candidates that are strictly valid JSON, syntactically valid in the target dialect,
  execute to the exact gold result in SQLite, AND stay concise.
- Penalizes candidates with execution failures, wrong results, non-JSON filler, or verbose plans.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from swiftsql.dialect import transpile_sql, validate_sql
from swiftsql.evaluation import execute_sqlite_sandbox, results_match
from swiftsql.prompts import parse_model_response


@dataclass
class ScoredCandidate:
    raw_text: str
    score: float
    exec_correct: bool
    syntax_valid: bool
    json_valid: bool
    length_chars: int


def score_candidate(
    record: Dict[str, Any],
    candidate_text: str,
) -> ScoredCandidate:
    """Score a single model completion on correctness + conciseness."""
    meta = record.get("meta", {})
    dialect = meta.get("dialect", "postgresql")
    gold_answerable = bool(meta.get("answerable", True))
    parsed = parse_model_response(candidate_text, default_dialect=dialect)

    length_chars = len(candidate_text or "")
    json_valid = bool(parsed["json_valid"])

    # Handle refusal examples
    if not gold_answerable:
        correct_refusal = (not parsed["answerable"]) and (not parsed["sql"])
        score = (100.0 if correct_refusal else -50.0) + (10.0 if json_valid else -20.0) - 0.02 * length_chars
        return ScoredCandidate(
            raw_text=candidate_text,
            score=score,
            exec_correct=correct_refusal,
            syntax_valid=correct_refusal,
            json_valid=json_valid,
            length_chars=length_chars,
        )

    # Answerable examples
    if not parsed["answerable"] or not parsed["sql"]:
        return ScoredCandidate(
            raw_text=candidate_text,
            score=-60.0,
            exec_correct=False,
            syntax_valid=False,
            json_valid=json_valid,
            length_chars=length_chars,
        )

    val = validate_sql(parsed["sql"], dialect=dialect, require_read_only=True)
    syntax_valid = val.valid
    exec_correct = False

    exec_ctx = meta.get("executable_context", "")
    gold_sqlite = meta.get("gold_sqlite_sql") or meta.get("gold_sql", "")
    if syntax_valid and exec_ctx and gold_sqlite:
        gold_out = execute_sqlite_sandbox(exec_ctx, gold_sqlite)
        pred_sqlite = transpile_sql(parsed["sql"], source_dialect=dialect, target_dialect="sqlite")
        if gold_out.success and pred_sqlite:
            pred_out = execute_sqlite_sandbox(exec_ctx, pred_sqlite)
            order_sensitive = "ORDER BY" in gold_sqlite.upper()
            exec_correct = pred_out.success and results_match(
                pred_out.rows, gold_out.rows, order_sensitive=order_sensitive
            )

    # Reward hierarchy:
    # 1. Execution correctness (+100)
    # 2. Dialect syntax & read-only validity (+25)
    # 3. Strict JSON format (+10)
    # 4. Auto-Think conciseness bonus: penalize overly verbose outputs (-0.03 per char)
    score = 0.0
    score += 100.0 if exec_correct else 0.0
    score += 25.0 if syntax_valid else -30.0
    score += 10.0 if json_valid else -20.0

    # Extra penalty if a simple query emitted a long plan
    if meta.get("complexity") == "simple" and parsed["plan"]:
        score -= 15.0

    score -= 0.03 * length_chars
    return ScoredCandidate(
        raw_text=candidate_text,
        score=score,
        exec_correct=exec_correct,
        syntax_valid=syntax_valid,
        json_valid=json_valid,
        length_chars=length_chars,
    )


def build_dpo_pair(
    record: Dict[str, Any],
    candidates: Sequence[str],
    min_score_gap: float = 15.0,
) -> Optional[Dict[str, Any]]:
    """Build a (prompt, chosen, rejected) DPO pair from N sampled candidates.

    Also falls back to gold assistant output as `chosen` if all sampled candidates failed,
    turning model failure modes directly into high-signal preference pairs.
    """
    if not candidates:
        return None

    scored = [score_candidate(record, c) for c in candidates]
    scored.sort(key=lambda s: s.score, reverse=True)

    best = scored[0]
    worst = scored[-1]

    messages = record["messages"]
    prompt_messages = [m for m in messages if m["role"] != "assistant"]
    gold_assistant = next((m["content"] for m in messages if m["role"] == "assistant"), None)

    # Case 1: Model generated at least one execution-correct answer AND at least one worse/verbose/wrong answer
    if best.exec_correct and (best.score - worst.score) >= min_score_gap and best.raw_text != worst.raw_text:
        return {
            "prompt": prompt_messages,
            "chosen": [{"role": "assistant", "content": best.raw_text}],
            "rejected": [{"role": "assistant", "content": worst.raw_text}],
            "meta": {
                "pair_source": "self_contrast",
                "chosen_score": round(best.score, 2),
                "rejected_score": round(worst.score, 2),
            },
        }

    # Case 2: All sampled candidates failed -> pair gold answer (chosen) vs worst failure (rejected)
    if (not best.exec_correct) and gold_assistant and worst.raw_text != gold_assistant:
        return {
            "prompt": prompt_messages,
            "chosen": [{"role": "assistant", "content": gold_assistant}],
            "rejected": [{"role": "assistant", "content": worst.raw_text}],
            "meta": {
                "pair_source": "gold_vs_failure",
                "chosen_score": 130.0,
                "rejected_score": round(worst.score, 2),
            },
        }

    return None
