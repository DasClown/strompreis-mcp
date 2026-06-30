"""Electricity price forecast model.

Strategy (v0.2):
  1. Historical DB → hour-of-day + day-of-week profiles
  2. Recent SMARD data → trend adjustment
  3. ML-ready: features + target for model training

v0.1: in-memory cache only
v0.2: SQLite-backed for persistent model training
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
from . import smard_client
from . import database


def _ms_to_dt(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def build_hour_profile_from_db(days: int = 30) -> dict:
    """Build average price profile from database history.
    
    Returns:
        dict: {hour: avg_price_ct_per_kwh} for 0..23
    """
    history = database.get_price_history(days=days)
    if not history:
        return {}

    hour_sums = {}
    hour_counts = {}

    for row in history:
        price = row.get("price_eur_mwh")
        if price is None:
            continue
        ts = row["timestamp_utc"]
        try:
            dt = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            continue
        hour = dt.hour
        # SMARD raw: ×100 EUR/MWh → ct/kWh needs /1000
        # 1 EUR/MWh = 0.1 ct/kWh, raw is 100× EUR/MWh
        price_ct = price / 1000.0
        hour_sums[hour] = hour_sums.get(hour, 0) + price_ct
        hour_counts[hour] = hour_counts.get(hour, 0) + 1

    profile = {}
    for hour in range(24):
        if hour_counts.get(hour, 0) > 0:
            profile[hour] = hour_sums[hour] / hour_counts[hour]
        else:
            profile[hour] = 10.0  # fallback
    return profile


def build_weekday_profile_from_db(days: int = 30) -> dict:
    """Build average price profile per day-of-week from DB."""
    history = database.get_price_history(days=days)
    if not history:
        return {}

    dow_sums = {}
    dow_counts = {}

    for row in history:
        price = row.get("price_eur_mwh")
        if price is None:
            continue
        ts = row["timestamp_utc"]
        try:
            dt = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            continue
        dow = dt.weekday()
        price_ct = price / 1000.0  # SMARD ×100 EUR/MWh → ct/kWh
        dow_sums[dow] = dow_sums.get(dow, 0) + price_ct
        dow_counts[dow] = dow_counts.get(dow, 0) + 1

    profile = {}
    for dow in range(7):
        if dow_counts.get(dow, 0) > 0:
            profile[dow] = dow_sums[dow] / dow_counts[dow]
        else:
            profile[dow] = 12.0
    return profile


def recent_trend_from_live(window_hours: int = 6) -> tuple:
    """Calculate recent price trend from live SMARD data.
    
    Returns:
        (current_avg_ct, trend_ct_per_hour, is_rising)
    """
    prices = smard_client.get_latest_prices()
    if not prices:
        return (10.0, 0.0, False)

    now = _now_ms()
    window_ms = window_hours * 3600 * 1000
    recent = [(ts, v) for ts, v in prices if ts >= now - window_ms]

    if len(recent) < 3:
        recent = prices[-24:]

    if not recent:
        return (10.0, 0.0, False)

    values = [v for _, v in recent]
    avg = sum(values) / len(values) / 1000.0  # SMARD ×100 EUR/MWh → ct/kWh

    # Simple trend: compare first half vs second half
    mid = len(recent) // 2
    if mid > 0:
        first_half = sum(v for _, v in recent[:mid]) / mid
        second_half = sum(v for _, v in recent[mid:]) / (len(recent) - mid)
        trend = (second_half - first_half) / max(mid, 1) / 1000.0
    else:
        trend = 0.0

    return (avg, trend, trend > 0)


def forecast(hours: int = 24) -> list:
    """Generate electricity price forecast.
    
    Combines:
      - Long-term hour profile from DB (30 days)
      - Day-of-week profile from DB
      - Recent trend from live SMARD data
    
    Args:
        hours: Number of hours to forecast (max 72)
    
    Returns:
        List of dicts with timestamp, price_ct, confidence, is_peak
    """
    hours = min(hours, 72)

    # 1. Historical profiles from database
    hour_profile = build_hour_profile_from_db(days=30)
    dow_profile = build_weekday_profile_from_db(days=30)

    # 2. Current market data
    prices = smard_client.get_latest_prices()
    avg_price, trend, is_rising = recent_trend_from_live()

    # 3. If we have DB history but no live data, use DB averages
    if not prices and hour_profile:
        avg_price = sum(hour_profile.values()) / max(len(hour_profile), 1)

    # 4. Generate forecast
    now = _now_ms()
    next_hour_ms = ((now // 3600000) + 1) * 3600000

    result = []
    for i in range(hours):
        ts = next_hour_ms + i * 3600000
        dt = _ms_to_dt(ts)
        hour = dt.hour
        is_weekend = dt.weekday() >= 5

        # Base price: hour profile (DB) with fallback
        base = hour_profile.get(hour, dow_profile.get(dt.weekday(), avg_price))

        # Weekend adjustment from DB
        if is_weekend and dt.weekday() in dow_profile:
            weekend_factor = dow_profile[dt.weekday()] / max(
                sum(dow_profile.get(d, 12.0) for d in range(5)) / 5, 1
            )
            base *= min(weekend_factor, 1.0)

        # Trend dampening (cautious — don't amplify noise)
        trend_adj = trend * min(i, 4) * 0.25
        forecast_price = max(base + trend_adj, base * 0.35)

        # Confidence degrades over time
        confidence = max(0.95 - (i * 0.025), 0.30)

        # Peak flag
        is_peak = (not is_weekend) and (8 <= hour < 20)

        result.append({
            "timestamp": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "price_ct": round(forecast_price, 2),
            "confidence": round(confidence, 2),
            "is_peak": is_peak,
        })

    return result


def _fallback_forecast(hours: int) -> list:
    """Generic fallback when no data available."""
    now = _now_ms()
    next_hour_ms = ((now // 3600000) + 1) * 3600000
    result = []

    for i in range(hours):
        ts = next_hour_ms + i * 3600000
        dt = _ms_to_dt(ts)
        hour = dt.hour
        is_weekend = dt.weekday() >= 5

        if 0 <= hour < 6:
            price = 8.0
        elif 6 <= hour < 8:
            price = 12.0
        elif 8 <= hour < 12:
            price = 14.0
        elif 12 <= hour < 14:
            price = 10.0
        elif 14 <= hour < 18:
            price = 13.0
        elif 18 <= hour < 22:
            price = 15.0
        else:
            price = 9.0

        if is_weekend:
            price *= 0.85

        result.append({
            "timestamp": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "price_ct": round(price, 2),
            "confidence": round(max(0.9 - (i * 0.02), 0.3), 2),
            "is_peak": (not is_weekend) and (8 <= hour < 20),
        })

    return result


def best_hours(count: int = 3) -> str:
    """Find the cheapest hours in the forecast period."""
    fc = forecast(hours=48)

    if not fc:
        return "Keine Prognose verfügbar."

    sorted_fc = sorted(fc, key=lambda x: x["price_ct"])
    best = sorted_fc[:count]

    if not best:
        return "Keine Prognose verfügbar."

    lines = [f"Günstigste {count} Stunden in den nächsten 48h:"]
    for b in sorted(best, key=lambda x: x["timestamp"]):
        lines.append(
            f"  {b['timestamp'][5:16]} → {b['price_ct']} ct/kWh "
            f"(Konfidenz: {b['confidence']:.0%})"
        )

    avg = sum(b["price_ct"] for b in best) / len(best)
    lines.append(f"Ø {avg:.1f} ct/kWh")
    lines.append("")
    lines.append("Tipp:")
    lines.append("  Waschmaschine/Trockner/Spüler in diesem Fenster laufen lassen.")
    lines.append("  Wallbox auf diese Zeit programmieren (dynamischer Tarif).")

    return "\n".join(lines)
