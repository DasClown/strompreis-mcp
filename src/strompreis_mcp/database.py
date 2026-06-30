"""
SQLite database layer for Strompreis MCP.

Persistence model:
  - price_data   → historical SMARD prices + generation data for ML training
  - api_keys     → monetization: tier-based API access
  - usage_log    → rate limiting + analytics

Database lives at STROMPREIS_DB_PATH (default: ~/.strompreis/strompreis.db)
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

DB_DIR = os.path.expanduser("~/.strompreis")
DB_PATH = os.environ.get("STROMPREIS_DB_PATH", os.path.join(DB_DIR, "strompreis.db"))

_local = threading.local()


def _get_connection() -> sqlite3.Connection:
    """Get thread-local database connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        os.makedirs(DB_DIR, exist_ok=True)
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
    return _local.conn


@contextmanager
def get_db():
    """Context manager for database access."""
    conn = _get_connection()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()


def init_db():
    """Create tables if they don't exist."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS price_data (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_utc   TEXT NOT NULL,       -- ISO 8601
                price_eur_mwh   REAL,                -- from SMARD (×100 EUR/MWh)
                load_mw         REAL,
                wind_offshore_mw REAL,
                wind_onshore_mw  REAL,
                solar_mw        REAL,
                collected_at    TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_price_data_ts
                ON price_data(timestamp_utc);

            CREATE TABLE IF NOT EXISTS price_meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            INSERT OR IGNORE INTO price_meta (key, value)
                VALUES ('schema_version', '1');

            CREATE TABLE IF NOT EXISTS api_keys (
                key         TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                tier        TEXT NOT NULL DEFAULT 'free'
                            CHECK(tier IN ('free','pro','enterprise')),
                daily_limit INTEGER NOT NULL DEFAULT 100,
                created_at  TEXT DEFAULT (datetime('now')),
                expires_at  TEXT,
                is_active   INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS usage_log (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key   TEXT,
                tool      TEXT NOT NULL,
                timestamp TEXT DEFAULT (datetime('now')),
                ip_address TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_usage_key
                ON usage_log(api_key, timestamp);
            CREATE INDEX IF NOT EXISTS idx_usage_day
                ON usage_log(date(timestamp));
        """)


# ─── price_data CRUD ─────────────────────────────────────

def store_prices(rows: list[dict]) -> int:
    """Bulk-insert price data rows. Returns count inserted."""
    if not rows:
        return 0
    with get_db() as conn:
        conn.executemany("""
            INSERT OR IGNORE INTO price_data
                (timestamp_utc, price_eur_mwh, load_mw,
                 wind_offshore_mw, wind_onshore_mw, solar_mw)
            VALUES
                (:timestamp_utc, :price_eur_mwh, :load_mw,
                 :wind_offshore_mw, :wind_onshore_mw, :solar_mw)
        """, rows)
        return conn.total_changes


def get_price_history(days: int = 30) -> list[dict]:
    """Get historical price data for model training."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT timestamp_utc, price_eur_mwh, load_mw,
                   wind_offshore_mw, wind_onshore_mw, solar_mw
            FROM price_data
            WHERE date(timestamp_utc) >= date('now', '-' || ? || ' days')
            ORDER BY timestamp_utc ASC
        """, (days,)).fetchall()
    return [dict(r) for r in rows]


def get_latest_db_timestamp() -> Optional[str]:
    """Get the most recent timestamp we have data for."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT timestamp_utc FROM price_data ORDER BY timestamp_utc DESC LIMIT 1"
        ).fetchone()
    return row["timestamp_utc"] if row else None


def get_price_count() -> int:
    """Total number of price data points stored."""
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) as cnt FROM price_data").fetchone()
    return row["cnt"]


# ─── api_keys CRUD ────────────────────────────────────────

def create_api_key(name: str, tier: str = "free",
                   daily_limit: int = 100) -> str:
    """Generate and store a new API key. Returns the key."""
    import secrets
    key = f"sp_{secrets.token_hex(16)}"
    with get_db() as conn:
        conn.execute("""
            INSERT INTO api_keys (key, name, tier, daily_limit)
            VALUES (?, ?, ?, ?)
        """, (key, name, tier, daily_limit))
    return key


def validate_api_key(key: str) -> Optional[dict]:
    """Check if key is valid and not over daily limit. Returns tier info or None."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT key, tier, daily_limit, is_active
            FROM api_keys
            WHERE key = ? AND is_active = 1
              AND (expires_at IS NULL OR expires_at > datetime('now'))
        """, (key,)).fetchone()
    if not row:
        return None

    # Check daily usage
    today_usage = conn.execute("""
        SELECT COUNT(*) as cnt FROM usage_log
        WHERE api_key = ? AND date(timestamp) = date('now')
    """, (key,)).fetchone()["cnt"]

    if today_usage >= row["daily_limit"]:
        return None  # rate limited

    return dict(row)


def log_usage(api_key: str, tool: str, ip: str = ""):
    """Record an API call."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO usage_log (api_key, tool, ip_address)
            VALUES (?, ?, ?)
        """, (api_key, tool, ip))


# ─── Maintenance ───────────────────────────────────────────

def vacuum():
    """Recover disk space. Run weekly."""
    with get_db() as conn:
        conn.execute("VACUUM")


# ─── Init on import ────────────────────────────────────────

init_db()
