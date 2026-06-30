"""
Automated data collector — fetches SMARD data and stores to SQLite.

Designed for cron:  ./collector.py collect   (fetch + store latest data)
                   ./collector.py status    (show data health)
                   ./collector.py vacuum    (weekly maintenance)
"""

import argparse
import sys
import time
from datetime import datetime, timezone

from . import smard_client
from . import database


def _ms_to_iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()


def cmd_collect(_args=None):
    """Fetch latest SMARD data and store to database."""
    print(f"[collector@{datetime.now():%H:%M:%S}] Fetching SMARD data...")

    # Get the latest timestamp block
    ts = smard_client.get_latest_price_timestamp()
    if not ts:
        print("  ⚠ No timestamps available from SMARD.")
        return 1

    print(f"  Latest block timestamp: {_ms_to_iso(ts)}")

    # Fetch prices
    prices_raw = smard_client.get_price_data(ts)
    # Filter valid entries
    prices = [(t, v) for t, v in prices_raw if v is not None]

    if not prices:
        # Try fetching older blocks if latest is empty
        timestamps = smard_client.get_available_timestamps()
        for older_ts in sorted(timestamps)[-3:]:
            prices_raw = smard_client.get_price_data(older_ts)
            prices = [(t, v) for t, v in prices_raw if v is not None]
            if prices:
                print(f"  Using older block: {_ms_to_iso(older_ts)}")
                break

    if not prices:
        print("  ⚠ No price data available after retries.")
        return 1

    print(f"  Got {len(prices)} price data points.")

    # Fetch generation data for this block
    solar = {t: v for t, v in smard_client.get_generation_data(ts, 1225)}
    wind_on = {t: v for t, v in smard_client.get_generation_data(ts, 1224)}
    wind_off = {t: v for t, v in smard_client.get_generation_data(ts, 1223)}
    load = {t: v for t, v in smard_client.get_generation_data(ts, 1226)}

    # Build rows
    rows = []
    for t_ms, price_val in prices:
        rows.append({
            "timestamp_utc": _ms_to_iso(t_ms),
            "price_eur_mwh": price_val,
            "load_mw": load.get(t_ms),
            "wind_offshore_mw": wind_off.get(t_ms),
            "wind_onshore_mw": wind_on.get(t_ms),
            "solar_mw": solar.get(t_ms),
        })

    stored = database.store_prices(rows)
    total = database.get_price_count()
    print(f"  ✅ Stored {stored} new rows (total: {total}).")
    return 0


def cmd_status(_args=None):
    """Show database health."""
    total = database.get_price_count()
    latest = database.get_latest_db_timestamp()
    print("📊 Strompreis DB Status")
    print(f"  Total rows:     {total}")
    print(f"  Latest data:    {latest or 'empty'}")
    print(f"  Database path:  {database.DB_PATH}")
    print(f"  DB file size:   ", end="")
    import os
    try:
        size = os.path.getsize(database.DB_PATH)
        if size > 1024 * 1024:
            print(f"{size / 1024 / 1024:.1f} MB")
        elif size > 1024:
            print(f"{size / 1024:.1f} KB")
        else:
            print(f"{size} B")
    except OSError:
        print("N/A")
    return 0


def cmd_vacuum(_args=None):
    """Weekly database maintenance."""
    print("🧹 Running VACUUM...")
    database.vacuum()
    print("  ✅ Done.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Strompreis data collector")
    parser.set_defaults(func=lambda _: parser.print_help())
    sub = parser.add_subparsers()

    p = sub.add_parser("collect", help="Fetch + store latest data")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("status", help="Show database health")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("vacuum", help="Weekly DB maintenance")
    p.set_defaults(func=cmd_vacuum)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
