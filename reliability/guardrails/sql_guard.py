"""SQL-safety guard.

Parses SQL with sqlglot and enforces a hard allow-list policy:
  * exactly one statement (blocks stacked-query injection),
  * the statement is a read-only SELECT / set-operation,
  * no DDL/DML/admin nodes (DROP/INSERT/UPDATE/DELETE/ALTER/PRAGMA/ATTACH/...),
  * only known tables are referenced (no sqlite_master / schema escape).

This is AST-based, not a `startswith("SELECT")` check — so it catches
``SELECT 1; DROP TABLE orders``, ``SELECT ... ATTACH``, comment tricks, etc.
"""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

ALLOWED_TABLES = {"orders", "tickets", "kpi_hourly", "anomaly_events", "hitl_queue"}

# Top-level statement types that are read-only.
_READ_ONLY_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Subquery)

# Any of these anywhere in the tree => reject.
_FORBIDDEN = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
    exp.Command,  # PRAGMA / ATTACH / VACUUM / etc.
    exp.Set,
)


@dataclass
class SqlVerdict:
    ok: bool
    reason: str
    sql: str

    def as_dict(self) -> dict:
        return {"ok": self.ok, "reason": self.reason, "sql": self.sql}


def validate_sql(sql: str) -> SqlVerdict:
    if not sql or not sql.strip():
        return SqlVerdict(False, "empty SQL", sql)

    try:
        statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except Exception as e:  # noqa: BLE001
        return SqlVerdict(False, f"unparseable SQL: {e}", sql)

    if len(statements) == 0:
        return SqlVerdict(False, "no statement parsed", sql)
    if len(statements) > 1:
        return SqlVerdict(False, "multiple statements are not allowed (possible stacked-query injection)", sql)

    stmt = statements[0]
    if not isinstance(stmt, _READ_ONLY_ROOTS):
        return SqlVerdict(False, f"only read-only SELECT queries are permitted, got {type(stmt).__name__}", sql)

    for node in stmt.walk():
        node = node[0] if isinstance(node, tuple) else node
        if isinstance(node, _FORBIDDEN):
            return SqlVerdict(False, f"forbidden operation: {type(node).__name__}", sql)

    # CTE-defined names (WITH x AS ...) are virtual tables, not real ones.
    cte_names = {(cte.alias_or_name or "").lower() for cte in stmt.find_all(exp.CTE)}
    for table in stmt.find_all(exp.Table):
        name = (table.name or "").lower()
        if name and name not in ALLOWED_TABLES and name not in cte_names:
            return SqlVerdict(False, f"access to table '{name}' is not allowed", sql)

    return SqlVerdict(True, "ok", sql)


def is_safe(sql: str) -> bool:
    return validate_sql(sql).ok
