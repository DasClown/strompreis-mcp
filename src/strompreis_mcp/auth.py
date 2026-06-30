"""
API key authentication + rate limiting for Strompreis MCP.

Two modes:
  1. KEYLESS (default) — runs freely, no auth, for local/dev use
  2. KEYED — validates API keys from STROMPREIS_API_KEY or X-API-Key header
"""

import os
import time
from datetime import datetime, date

from . import database

# Global rate limit counter for keyless mode
_keyless_usage: list[float] = []
_KEYLESS_LIMIT = 100       # requests per window
_KEYLESS_WINDOW = 86400    # 24 hours in seconds


def authenticate(tool_name: str = "") -> bool:
    """Check if the current request is allowed.
    
    In keyless mode: simple global rate limit (100 req/day).
    In keyed mode: validate API key + per-key daily limit.
    
    Returns True if allowed, False if rate limited.
    """
    api_key = os.environ.get("STROMPREIS_API_KEY", "")
    
    if api_key:
        # KEYED MODE
        key_info = database.validate_api_key(api_key)
        if key_info is None:
            return False
        database.log_usage(api_key, tool_name)
        return True
    else:
        # KEYLESS MODE — simple global rate limit
        return _check_keyless_limit()


def _check_keyless_limit() -> bool:
    """Global rate limit for keyless (local) mode."""
    global _keyless_usage
    now = time.time()
    # Prune old entries
    cutoff = now - _KEYLESS_WINDOW
    _keyless_usage = [t for t in _keyless_usage if t > cutoff]
    
    if len(_keyless_usage) >= _KEYLESS_LIMIT:
        return False
    
    _keyless_usage.append(now)
    return True


def get_usage_stats() -> dict:
    """Return usage statistics for reporting."""
    total_keys = 0
    with database.get_db() as conn:
        total_keys = conn.execute(
            "SELECT COUNT(*) as c FROM api_keys WHERE is_active=1"
        ).fetchone()["c"]
        today_calls = conn.execute(
            "SELECT COUNT(*) as c FROM usage_log WHERE date(timestamp)=date('now')"
        ).fetchone()["c"]
    
    return {
        "mode": "keyed" if os.environ.get("STROMPREIS_API_KEY") else "keyless",
        "total_active_keys": total_keys,
        "today_calls": today_calls,
    }
