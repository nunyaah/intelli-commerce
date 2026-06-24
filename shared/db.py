import sqlite3
import os
import time

DB_PATH = os.environ.get("DB_PATH", "/data/commerce.db")


def _db_path() -> str:
    # Read at call time so the reliability suite can point the agent at a
    # deterministic fixture DB by setting DB_PATH, without import-order issues.
    return os.environ.get("DB_PATH", DB_PATH)


def get_conn():
    conn = sqlite3.connect(_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    # Wait up to 30s for a lock instead of failing instantly under the
    # concurrent writes from the generator threads + pipeline.
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _enable_wal():
    # WAL is a persistent property of the DB file, so it only needs to be set
    # once (it lets many processes read while one writes). Switching journal
    # mode needs a brief exclusive lock and does NOT honour busy_timeout, so it
    # can raise "database is locked" if another service is mid-write at startup.
    # Retry briefly; whichever service wins, the rest see WAL already enabled.
    for _ in range(20):
        try:
            conn = sqlite3.connect(_db_path(), timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.close()
            return
        except sqlite3.OperationalError:
            time.sleep(0.5)


def init_db():
    _enable_wal()
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            product_id TEXT,
            product_name TEXT,
            category TEXT,
            price REAL,
            quantity INTEGER,
            total REAL,
            region TEXT,
            payment_method TEXT,
            is_fraud INTEGER DEFAULT 0,
            risk_score REAL DEFAULT 0.0,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            processed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id TEXT PRIMARY KEY,
            order_id TEXT,
            user_id TEXT,
            category TEXT,
            urgency TEXT,
            subject TEXT,
            message TEXT,
            sentiment REAL DEFAULT 0.0,
            status TEXT DEFAULT 'open',
            resolution_time_minutes INTEGER,
            created_at TEXT,
            processed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS kpi_hourly (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hour TEXT UNIQUE,
            revenue REAL DEFAULT 0.0,
            order_count INTEGER DEFAULT 0,
            avg_order_value REAL DEFAULT 0.0,
            ticket_count INTEGER DEFAULT 0,
            resolved_tickets INTEGER DEFAULT 0,
            fraud_count INTEGER DEFAULT 0,
            refund_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS anomaly_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            description TEXT,
            severity TEXT,
            metric_value REAL,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS hitl_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT,
            trace_id TEXT,
            query TEXT,
            anomaly_type TEXT,
            description TEXT,
            metric_value REAL,
            status TEXT DEFAULT 'pending',
            action TEXT,
            created_at TEXT,
            resolved_at TEXT
        );
    """)
    _migrate(conn)
    conn.commit()
    conn.close()


def _migrate(conn):
    """Idempotently add columns introduced after a table was first created.
    CREATE TABLE IF NOT EXISTS never alters an existing table, so deployments
    with an older DB on a persistent volume need this to self-heal."""
    expected = {
        "hitl_queue": {"trace_id": "TEXT", "query": "TEXT"},
    }
    for table, cols in expected.items():
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, coltype in cols.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
