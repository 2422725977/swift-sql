"""Multi-dialect SQL parsing, transpilation, safety checks, and complexity analysis."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import sqlglot
from sqlglot import exp

logging.getLogger("sqlglot").setLevel(logging.ERROR)

SUPPORTED_DIALECTS = ("sqlite", "postgresql", "mysql")

_DIALECT_MAP = {
    "sqlite": "sqlite",
    "postgres": "postgres",
    "postgresql": "postgres",
    "pg": "postgres",
    "mysql": "mysql",
    "mariadb": "mysql",
}

_FORBIDDEN_EXPRESSIONS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.Command,
    exp.Merge,
    exp.Grant,
    exp.Revoke,
)


def normalize_dialect(dialect: str) -> str:
    """Normalize dialect alias to canonical name: sqlite, postgresql, or mysql."""
    key = (dialect or "sqlite").strip().lower()
    if key in ("postgres", "postgresql", "pg"):
        return "postgresql"
    if key in ("mysql", "mariadb"):
        return "mysql"
    if key == "sqlite":
        return "sqlite"
    raise ValueError(f"Unsupported SQL dialect: {dialect!r}. Choose from {SUPPORTED_DIALECTS}.")


def _to_sqlglot_dialect(dialect: str) -> str:
    return _DIALECT_MAP[normalize_dialect(dialect)]


@dataclass
class ValidationResult:
    valid: bool
    read_only: bool
    dialect: str
    normalized_sql: str = ""
    tables: List[str] = None
    error: str = ""

    def __post_init__(self) -> None:
        if self.tables is None:
            self.tables = []


def transpile_sql(sql: str, source_dialect: str = "sqlite", target_dialect: str = "postgresql") -> Optional[str]:
    """Transpile a single SQL query between sqlite/postgresql/mysql using sqlglot.

    Returns None if parsing or transpilation fails.
    """
    if not sql or not sql.strip():
        return None
    src = _to_sqlglot_dialect(source_dialect)
    tgt = _to_sqlglot_dialect(target_dialect)
    try:
        parsed = sqlglot.parse(sql.strip(), read=src)
        if not parsed or len(parsed) != 1 or parsed[0] is None:
            return None
        out = parsed[0].sql(dialect=tgt)
        # Round-trip check in target dialect to ensure syntax validity
        reparsed = sqlglot.parse_one(out, read=tgt)
        if reparsed is None:
            return None
        return out.strip()
    except Exception:
        return None


def validate_sql(
    sql: str,
    dialect: str = "postgresql",
    require_read_only: bool = True,
) -> ValidationResult:
    """Validate SQL syntax in the target dialect and optionally enforce read-only safety."""
    norm_dialect = normalize_dialect(dialect)
    sg_dialect = _to_sqlglot_dialect(norm_dialect)

    if not sql or not sql.strip():
        return ValidationResult(
            valid=False,
            read_only=True,
            dialect=norm_dialect,
            error="Empty SQL statement.",
        )

    try:
        statements = sqlglot.parse(sql.strip(), read=sg_dialect)
    except Exception as exc:
        return ValidationResult(
            valid=False,
            read_only=False,
            dialect=norm_dialect,
            error=f"Syntax error ({norm_dialect}): {exc}",
        )

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        return ValidationResult(
            valid=False,
            read_only=False,
            dialect=norm_dialect,
            error=f"Expected exactly 1 SQL statement, found {len(statements)}.",
        )

    stmt = statements[0]
    read_only = True
    for forbidden in _FORBIDDEN_EXPRESSIONS:
        if isinstance(stmt, forbidden) or stmt.find(forbidden) is not None:
            read_only = False
            break

    # Explicitly allow SELECT / UNION / INTERSECT / EXCEPT / WITH (CTE wrapping SELECT)
    if not isinstance(stmt, (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Subquery)):
        read_only = False

    tables = sorted({t.name for t in stmt.find_all(exp.Table) if t.name})

    if require_read_only and not read_only:
        return ValidationResult(
            valid=False,
            read_only=False,
            dialect=norm_dialect,
            normalized_sql=stmt.sql(dialect=sg_dialect),
            tables=tables,
            error="Write or DDL/DCL operations are blocked; only read-only SELECT queries are allowed.",
        )

    return ValidationResult(
        valid=True,
        read_only=read_only,
        dialect=norm_dialect,
        normalized_sql=stmt.sql(dialect=sg_dialect),
        tables=tables,
    )


def analyze_complexity(sql: str, dialect: str = "sqlite") -> Tuple[str, bool, List[str]]:
    """Classify SQL query complexity for Auto-Think routing.

    Returns:
        (level, needs_plan, tables)
        - level: "simple" | "medium" | "complex"
        - needs_plan: True if Auto-Think should emit a concise 1-sentence plan before SQL
        - tables: sorted list of referenced table names
    """
    sg_dialect = _to_sqlglot_dialect(dialect)
    try:
        stmt = sqlglot.parse_one(sql.strip(), read=sg_dialect)
    except Exception:
        return ("medium", True, [])

    joins = list(stmt.find_all(exp.Join))
    subqueries = list(stmt.find_all(exp.Subquery))
    ctes = list(stmt.find_all(exp.CTE))
    windows = list(stmt.find_all(exp.Window))
    unions = list(stmt.find_all(exp.Union))
    has_having = stmt.find(exp.Having) is not None
    has_group = stmt.find(exp.Group) is not None
    tables = sorted({t.name for t in stmt.find_all(exp.Table) if t.name})

    score = (
        len(joins) * 2
        + len(subqueries) * 2
        + len(ctes) * 2
        + len(windows) * 2
        + len(unions) * 2
        + (1 if has_having else 0)
        + (1 if has_group and len(tables) > 1 else 0)
    )

    if score == 0 and len(tables) <= 1:
        return ("simple", False, tables)
    if score <= 2:
        # Fast Auto-Think: simple 1-JOIN queries skip plan for lower latency
        return ("medium", False, tables)
    return ("complex", True, tables)


def extract_schema_tables_and_columns(schema_sql: str) -> Dict[str, List[str]]:
    """Extract {table_name: [col1, col2, ...]} from CREATE TABLE statements."""
    result: Dict[str, List[str]] = {}
    if not schema_sql:
        return result

    # Strip INSERT statements to speed up parsing and avoid noise
    ddl_chunks = re.findall(
        r"CREATE\s+(?:TEMP\s+|TEMPORARY\s+)?TABLE\s+.*?\);",
        schema_sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    parse_target = "\n".join(ddl_chunks) if ddl_chunks else schema_sql

    try:
        statements = sqlglot.parse(parse_target, read="sqlite")
    except Exception:
        statements = []

    for stmt in statements:
        if not isinstance(stmt, exp.Create):
            continue
        table_expr = stmt.find(exp.Table)
        if table_expr is None or not table_expr.name:
            continue
        table_name = table_expr.name
        cols: List[str] = []
        for col_def in stmt.find_all(exp.ColumnDef):
            if col_def.name:
                cols.append(col_def.name)
        if cols:
            result[table_name] = cols

    return result


def extract_referenced_columns(sql: str, dialect: str = "sqlite") -> Set[str]:
    """Return lowercase column names referenced by a SQL query."""
    try:
        stmt = sqlglot.parse_one(sql.strip(), read=_to_sqlglot_dialect(dialect))
    except Exception:
        return set()
    return {col.name.lower() for col in stmt.find_all(exp.Column) if col.name}


def extract_ddl_only(context_sql: str) -> str:
    """Keep CREATE TABLE statements only (drop INSERT INTO seed rows) for clean prompt schemas."""
    if not context_sql:
        return ""
    ddl_chunks = re.findall(
        r"CREATE\s+(?:TEMP\s+|TEMPORARY\s+)?TABLE\s+.*?\);",
        context_sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if ddl_chunks:
        return "\n".join(chunk.strip() for chunk in ddl_chunks)
    return context_sql.strip()


def drop_column_from_ddl(ddl_sql: str, column_to_drop: str) -> Optional[str]:
    """Remove a specific column definition from CREATE TABLE DDL to synthesize refusal samples."""
    if not ddl_sql or not column_to_drop:
        return None
    target_lower = column_to_drop.lower()
    try:
        statements = sqlglot.parse(ddl_sql, read="sqlite")
    except Exception:
        return None

    removed = False
    new_ddls: List[str] = []
    for stmt in statements:
        if not isinstance(stmt, exp.Create):
            continue
        schema_expr = stmt.this
        if not isinstance(schema_expr, exp.Schema):
            continue
        kept_exprs = []
        col_defs_remaining = 0
        for item in schema_expr.expressions:
            if isinstance(item, exp.ColumnDef) and item.name.lower() == target_lower:
                removed = True
                continue
            # Also drop FK/PK constraints mentioning the dropped column to keep DDL valid
            if not isinstance(item, exp.ColumnDef):
                col_refs = {c.name.lower() for c in item.find_all(exp.Column) if c.name}
                id_refs = {i.name.lower() for i in item.find_all(exp.Identifier) if i.name}
                if target_lower in col_refs or target_lower in id_refs:
                    continue
            else:
                col_defs_remaining += 1
            kept_exprs.append(item)

        if col_defs_remaining == 0:
            return None
        schema_expr.set("expressions", kept_exprs)
        new_ddls.append(stmt.sql(dialect="sqlite") + ";")

    if not removed or not new_ddls:
        return None
    return "\n".join(new_ddls)
