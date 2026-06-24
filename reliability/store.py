"""SQLite persistence for traces, eval runs, guardrail events, and HITL labels.

This is the always-on source of truth that powers the dashboard and the gate.
It is intentionally self-contained (no external services) so the suite runs in
CI and on a laptop. It lives in its own DB file (RELIABILITY_DB), separate from
the agent's operational data.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional

from reliability.config import reliability_db_path
from reliability.tracing.schema import Span, Trace


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn(path: Optional[str] = None) -> sqlite3.Connection:
    path = path or reliability_db_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_traces (
    trace_id       TEXT PRIMARY KEY,
    thread_id      TEXT,
    query          TEXT,
    final_answer   TEXT,
    agent_version  TEXT,
    source         TEXT,
    started_at     TEXT,
    ended_at       TEXT,
    duration_ms    REAL,
    input_tokens   INTEGER,
    output_tokens  INTEGER,
    cost_usd       REAL,
    num_llm_calls  INTEGER,
    num_tool_calls INTEGER,
    error          TEXT
);

CREATE TABLE IF NOT EXISTS spans (
    span_id     TEXT PRIMARY KEY,
    trace_id    TEXT,
    parent_id   TEXT,
    name        TEXT,
    kind        TEXT,
    start_ms    REAL,
    end_ms      REAL,
    duration_ms REAL,
    status      TEXT,
    error       TEXT,
    attributes  TEXT
);
CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id);

CREATE TABLE IF NOT EXISTS eval_runs (
    id              TEXT PRIMARY KEY,
    dataset_version TEXT,
    agent_version   TEXT,
    agent_label     TEXT,
    mode            TEXT,
    seed            INTEGER,
    created_at      TEXT,
    num_cases       INTEGER,
    config          TEXT,
    summary         TEXT
);

CREATE TABLE IF NOT EXISTS eval_results (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    eval_run_id  TEXT,
    case_id      TEXT,
    trace_id     TEXT,
    grader       TEXT,
    score        REAL,
    passed       INTEGER,
    weight       REAL,
    details      TEXT
);
CREATE INDEX IF NOT EXISTS idx_results_run ON eval_results(eval_run_id);

CREATE TABLE IF NOT EXISTS guardrail_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id    TEXT,
    thread_id   TEXT,
    guard       TEXT,
    action      TEXT,
    severity    TEXT,
    detail      TEXT,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_guardrail_trace ON guardrail_events(trace_id);

-- HITL review -> label -> eval-dataset loop. Reviewers correct/confirm expected
-- behaviour for a real trace; exported labels feed the next dataset version.
CREATE TABLE IF NOT EXISTS dataset_labels (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_trace_id TEXT,
    query           TEXT,
    expected        TEXT,
    label_status    TEXT DEFAULT 'pending',  -- pending | labeled | rejected
    labeled_by      TEXT,
    note            TEXT,
    exported        INTEGER DEFAULT 0,
    created_at      TEXT,
    updated_at      TEXT
);
"""


def init_store(path: Optional[str] = None) -> None:
    # WAL is a persistent DB property; enabling it lets the API read while the
    # CLI writes during a live demo.
    p = path or reliability_db_path()
    parent = os.path.dirname(p)
    if parent:
        os.makedirs(parent, exist_ok=True)
    for _ in range(20):
        try:
            c = sqlite3.connect(p, timeout=30)
            c.execute("PRAGMA journal_mode=WAL")
            c.close()
            break
        except sqlite3.OperationalError:
            time.sleep(0.2)
    conn = get_conn(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


# --- Traces ------------------------------------------------------------------

def save_trace(trace: Trace, path: Optional[str] = None) -> None:
    conn = get_conn(path)
    try:
        h = trace.header_row()
        conn.execute(
            """INSERT OR REPLACE INTO agent_traces
               (trace_id, thread_id, query, final_answer, agent_version, source,
                started_at, ended_at, duration_ms, input_tokens, output_tokens,
                cost_usd, num_llm_calls, num_tool_calls, error)
               VALUES (:trace_id,:thread_id,:query,:final_answer,:agent_version,:source,
                :started_at,:ended_at,:duration_ms,:input_tokens,:output_tokens,
                :cost_usd,:num_llm_calls,:num_tool_calls,:error)""",
            h,
        )
        conn.execute("DELETE FROM spans WHERE trace_id = ?", (trace.trace_id,))
        for s in trace.spans:
            conn.execute(
                """INSERT OR REPLACE INTO spans
                   (span_id, trace_id, parent_id, name, kind, start_ms, end_ms,
                    duration_ms, status, error, attributes)
                   VALUES (:span_id,:trace_id,:parent_id,:name,:kind,:start_ms,:end_ms,
                    :duration_ms,:status,:error,:attributes)""",
                s.to_row(),
            )
        conn.commit()
    finally:
        conn.close()


def load_trace(trace_id: str, path: Optional[str] = None) -> Optional[Trace]:
    conn = get_conn(path)
    try:
        row = conn.execute("SELECT * FROM agent_traces WHERE trace_id = ?", (trace_id,)).fetchone()
        if not row:
            return None
        span_rows = conn.execute(
            "SELECT * FROM spans WHERE trace_id = ? ORDER BY start_ms", (trace_id,)
        ).fetchall()
    finally:
        conn.close()
    spans = [Span.from_row(dict(r)) for r in span_rows]
    return Trace(
        trace_id=row["trace_id"],
        query=row["query"],
        thread_id=row["thread_id"],
        final_answer=row["final_answer"] or "",
        agent_version=json.loads(row["agent_version"]) if row["agent_version"] else {},
        source=row["source"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        error=row["error"],
        spans=spans,
    )


def list_traces(limit: int = 100, source: Optional[str] = None, path: Optional[str] = None) -> list[dict]:
    conn = get_conn(path)
    try:
        if source:
            rows = conn.execute(
                "SELECT * FROM agent_traces WHERE source = ? ORDER BY started_at DESC LIMIT ?",
                (source, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM agent_traces ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# --- Eval runs / results -----------------------------------------------------

def save_eval_run(
    run_id: str,
    dataset_version: str,
    agent_version: dict,
    agent_label: str,
    mode: str,
    seed: int,
    num_cases: int,
    config: dict,
    summary: dict,
    path: Optional[str] = None,
) -> None:
    conn = get_conn(path)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO eval_runs
               (id, dataset_version, agent_version, agent_label, mode, seed,
                created_at, num_cases, config, summary)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id,
                dataset_version,
                json.dumps(agent_version, default=str),
                agent_label,
                mode,
                seed,
                _utcnow(),
                num_cases,
                json.dumps(config, default=str),
                json.dumps(summary, default=str),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def save_eval_result(
    eval_run_id: str,
    case_id: str,
    trace_id: str,
    grader: str,
    score: float,
    passed: bool,
    weight: float,
    details: dict,
    path: Optional[str] = None,
) -> None:
    conn = get_conn(path)
    try:
        conn.execute(
            """INSERT INTO eval_results
               (eval_run_id, case_id, trace_id, grader, score, passed, weight, details)
               VALUES (?,?,?,?,?,?,?,?)""",
            (eval_run_id, case_id, trace_id, grader, score, int(passed), weight,
             json.dumps(details, default=str)),
        )
        conn.commit()
    finally:
        conn.close()


def get_eval_run(run_id: str, path: Optional[str] = None) -> Optional[dict]:
    conn = get_conn(path)
    try:
        row = conn.execute("SELECT * FROM eval_runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        results = conn.execute(
            "SELECT * FROM eval_results WHERE eval_run_id = ?", (run_id,)
        ).fetchall()
    finally:
        conn.close()
    d = dict(row)
    d["agent_version"] = json.loads(d["agent_version"]) if d["agent_version"] else {}
    d["config"] = json.loads(d["config"]) if d["config"] else {}
    d["summary"] = json.loads(d["summary"]) if d["summary"] else {}
    d["results"] = [
        dict(r) | {"details": json.loads(r["details"]) if r["details"] else {}}
        for r in results
    ]
    return d


def list_eval_runs(limit: int = 50, path: Optional[str] = None) -> list[dict]:
    conn = get_conn(path)
    try:
        rows = conn.execute(
            "SELECT id, dataset_version, agent_label, mode, seed, created_at, num_cases, summary "
            "FROM eval_runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["summary"] = json.loads(d["summary"]) if d["summary"] else {}
        out.append(d)
    return out


def latest_eval_run(agent_label: Optional[str] = None, path: Optional[str] = None) -> Optional[dict]:
    conn = get_conn(path)
    try:
        if agent_label:
            row = conn.execute(
                "SELECT id FROM eval_runs WHERE agent_label = ? ORDER BY created_at DESC LIMIT 1",
                (agent_label,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM eval_runs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
    finally:
        conn.close()
    return get_eval_run(row["id"], path) if row else None


# --- Guardrail events --------------------------------------------------------

def log_guardrail_event(
    trace_id: Optional[str],
    thread_id: Optional[str],
    guard: str,
    action: str,
    severity: str,
    detail: dict,
    path: Optional[str] = None,
) -> None:
    conn = get_conn(path)
    try:
        conn.execute(
            """INSERT INTO guardrail_events (trace_id, thread_id, guard, action, severity, detail, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (trace_id, thread_id, guard, action, severity, json.dumps(detail, default=str), _utcnow()),
        )
        conn.commit()
    finally:
        conn.close()


def list_guardrail_events(limit: int = 100, path: Optional[str] = None) -> list[dict]:
    conn = get_conn(path)
    try:
        rows = conn.execute(
            "SELECT * FROM guardrail_events ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["detail"] = json.loads(d["detail"]) if d["detail"] else {}
        out.append(d)
    return out


# --- HITL dataset labels -----------------------------------------------------

def create_label(
    source_trace_id: Optional[str],
    query: str,
    expected: dict,
    path: Optional[str] = None,
) -> int:
    conn = get_conn(path)
    try:
        cur = conn.execute(
            """INSERT INTO dataset_labels (source_trace_id, query, expected, label_status, created_at, updated_at)
               VALUES (?,?,?, 'pending', ?, ?)""",
            (source_trace_id, query, json.dumps(expected, default=str), _utcnow(), _utcnow()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_label(
    label_id: int,
    expected: dict,
    label_status: str,
    labeled_by: str,
    note: str = "",
    path: Optional[str] = None,
) -> None:
    conn = get_conn(path)
    try:
        conn.execute(
            """UPDATE dataset_labels
               SET expected = ?, label_status = ?, labeled_by = ?, note = ?, updated_at = ?
               WHERE id = ?""",
            (json.dumps(expected, default=str), label_status, labeled_by, note, _utcnow(), label_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_labels(status: Optional[str] = None, path: Optional[str] = None) -> list[dict]:
    conn = get_conn(path)
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM dataset_labels WHERE label_status = ? ORDER BY created_at DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM dataset_labels ORDER BY created_at DESC"
            ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["expected"] = json.loads(d["expected"]) if d["expected"] else {}
        out.append(d)
    return out


def mark_labels_exported(label_ids: list[int], path: Optional[str] = None) -> None:
    if not label_ids:
        return
    conn = get_conn(path)
    try:
        conn.executemany(
            "UPDATE dataset_labels SET exported = 1, updated_at = ? WHERE id = ?",
            [(_utcnow(), lid) for lid in label_ids],
        )
        conn.commit()
    finally:
        conn.close()
