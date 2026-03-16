"""
db.py - Database initialization and access layer (SQLite)
"""
import sqlite3
import os
import threading

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'backupman.db')
_local = threading.local()


def get_conn():
    """Return a thread-local SQLite connection."""
    if not hasattr(_local, 'conn') or _local.conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


def init_db():
    """Create all tables if not present."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    c = conn.cursor()

    # --- Schedules ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            enabled     INTEGER NOT NULL DEFAULT 1,
            source_path TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'local',  -- 'local' | 'network'
            source_cred_id TEXT,
            schedule_type TEXT NOT NULL,  -- 'daily'|'weekly'|'monthly'|'interval'|'calendar'
            schedule_config TEXT NOT NULL DEFAULT '{}',  -- JSON
            delete_old  INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            last_run    TEXT,
            next_run    TEXT,
            status      TEXT NOT NULL DEFAULT 'idle'  -- 'idle'|'running'|'success'|'error'
        )
    """)

    # --- Destinations (multiple per schedule) ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS destinations (
            id          TEXT PRIMARY KEY,
            schedule_id TEXT NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
            dest_path   TEXT NOT NULL,
            dest_type   TEXT NOT NULL DEFAULT 'local',  -- 'local'|'network'
            dest_cred_id TEXT,
            name_template TEXT NOT NULL DEFAULT '{name}_{date}_{id}.{ext}',
            ext         TEXT NOT NULL DEFAULT 'bak',
            sort_order  INTEGER NOT NULL DEFAULT 0
        )
    """)

    # --- Stored credentials (encrypted at rest with base64 obfuscation) ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS credentials (
            id          TEXT PRIMARY KEY,
            label       TEXT NOT NULL,
            server      TEXT NOT NULL,
            username    TEXT NOT NULL,
            password_b64 TEXT NOT NULL,
            created_at  TEXT NOT NULL
        )
    """)

    # --- Backup run history ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS run_history (
            id          TEXT PRIMARY KEY,
            schedule_id TEXT NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
            started_at  TEXT NOT NULL,
            finished_at TEXT,
            status      TEXT NOT NULL DEFAULT 'running',  -- 'running'|'success'|'error'|'cancelled'
            bytes_copied INTEGER,
            error_msg   TEXT,
            triggered_by TEXT NOT NULL DEFAULT 'scheduler'  -- 'scheduler'|'manual'|'missed'
        )
    """)

    # --- Per-run destination results ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS run_destinations (
            id          TEXT PRIMARY KEY,
            run_id      TEXT NOT NULL REFERENCES run_history(id) ON DELETE CASCADE,
            dest_id     TEXT NOT NULL,
            dest_path   TEXT NOT NULL,
            output_name TEXT,
            status      TEXT NOT NULL DEFAULT 'pending',
            bytes_copied INTEGER,
            error_msg   TEXT
        )
    """)

    # --- Missed schedule tracking ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS missed_runs (
            id          TEXT PRIMARY KEY,
            schedule_id TEXT NOT NULL REFERENCES schedules(id) ON DELETE CASCADE,
            scheduled_at TEXT NOT NULL,
            recovered   INTEGER NOT NULL DEFAULT 0,
            recovered_at TEXT
        )
    """)

    conn.commit()
    conn.close()
