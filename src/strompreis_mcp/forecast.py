"""Electricity price forecast model.

Uses a simple approach combining:
1. Historical average price patterns (hour-of-day, day-of-week)
2. Recent price trend
3. Weather-adjusted expectation (via solar/wind generation)

This is intentionally simple (Baseline) — no ML, ~100 lines.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
from . import smard_client


def _ms_to_dt(ts_ms: int) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)


def _hour_of_day(ts_ms: int) -> int:
    return _ms_to_dt(ts_ms).hour


def _day_of_week(ts_ms: int) -> int:
    return _ms_to_dt(ts_ms).weekday()


def _is_weekend(ts_ms: int) -> bool:
    return _day_of_week(ts_ms) >= 5


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def build_hour_profile(prices: list) -> dict:
    """Build average price profile per hour of day.
    
    Returns:
        dict: {hour: avg_price_ct_per_kwh}
    """
    hour_sums = {}
    hour_counts = {}
    
    for ts, val in prices:
        if val is None:
            continue
        hour = _hour_of_day(ts)
        price_ct = val / 1000.0  # SMARD (×100 EUR/MWh) → ct/kWh
        hour_sums.setdefault(hour, 0)
        hour_sums[hour] += price_ct
        hour_counts.setdefault(hour, 0)
        hour_counts[hour] += 1
    
    profile = {}
    for hour in range(24):
        if hour_counts.get(hour, 0) > 0:
            profile[hour] = hour_sums[hour] / hour_counts[hour]
        else:
            profile[hour] = 10.0  # fallback
    
    return profile


def recent_trend(prices: list, window_hours: int = 6) -> tuple:
    """Calculate recent price trend.
    
    Returns:
        (current_avg_ct, trend_ct_per_hour, is_rising)
    """
    if not prices:
        return (10.0, 0.0, False)
    
    now = _now_ms()
    window_ms = window_hours * 3600 * 1000
    
    recent = [(ts, v) for ts, v in prices if ts >= now - window_ms]
    if len(recent) < 3:
        recent = prices[-24:]  # last 24 entries
    
    if not recent:
        return (10.0, 0.0, False)
    
    # Simple linear trend
    values = [v for _, v in recent]
    avg = sum(values) / len(values) / 1000.0
    
    # Calculate trend (in ×100 EUR/MWh per step)
    mid = len(recent) // 2
    if mid > 0:
        first_half = sum(v for _, v in recent[:mid]) / mid
        second_half = sum(v for _, v in recent[mid:]) / (len(recent) - mid)
        trend_raw = (second_half - first_half) / max(len(recent) // 4, 1)
        trend = trend_raw / 1000.0  # Convert to ct/kWh change per hour
    else:
        trend = 0.0
    
    return (avg, trend, trend > 0)


def forecast(hours: int = 24) -> list:
    """Generate electricity price forecast.
    
    Args:
        hours: Number of hours to forecast (default 24, max 72)
    
    Returns:
        List of dicts:
        {"timestamp": "2026-06-28T14:00:00Z", "price_ct": 8.2, 
         "confidence": 0.85, "is_peak": False}
    """
    hours = min(hours, 72)
    
    # Get historical data
    prices = smard_client.get_latest_prices()
    
    if not prices:
        return _fallback_forecast(hours)
    
    # Build hour profile from historical data
    profile = build_hour_profile(prices)
    
    # Get recent trend
    avg_price, trend, is_rising = recent_trend(prices)
    
    # Generate forecast starting from now
    now = _now_ms()
    # Round to next hour
    next_hour_ms = ((now // 3600000) + 1) * 3600000
    
    result = []
    for i in range(hours):
        ts = next_hour_ms + i * 3600000
        dt = _ms_to_dt(ts)
        hour = dt.hour
        is_weekend = dt.weekday() >= 5
        
        # Base price from hour profile
        base = profile.get(hour, avg_price)
        
        # Weekend adjustment
        if is_weekend:
            base *= 0.85
        
        # Apply trend (very cautiously)
        trend_adjustment = trend * min(i, 4) * 0.3
        forecast_price = max(base + trend_adjustment, base * 0.4)
        
        # Confidence decreases with time
        confidence = max(0.95 - (i * 0.025), 0.30)
        
        # Peak hours (workdays, 8-20)
        is_peak = (not is_weekend) and (8 <= hour < 20)
        
        result.append({
            "timestamp": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "price_ct": round(forecast_price, 2),
            "confidence": round(confidence, 2),
            "is_peak": is_peak,
        })
    
    return result


def _fallback_forecast(hours: int) -> list:
    """Fallback when no SMARD data available."""
    now = _now_ms()
    next_hour_ms = ((now // 3600000) + 1) * 3600000
    
    result = []
    for i in range(hours):
        ts = next_hour_ms + i * 3600000
        dt = _ms_to_dt(ts)
        hour = dt.hour
        is_weekend = dt.weekday() >= 5
        
        # Generic German electricity price profile
        if 0 <= hour < 6:
            price = 8.0  # low
        elif 6 <= hour < 8:
            price = 12.0  # morning ramp
        elif 8 <= hour < 12:
            price = 14.0  # morning peak
        elif 12 <= hour < 14:
            price = 10.0  # lunch dip
        elif 14 <= hour < 18:
            price = 13.0  # afternoon
        elif 18 <= hour < 22:
            price = 15.0  # evening peak
        else:
            price = 9.0  # night
        
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
    """Find the cheapest hours in the forecast period.
    
    Args:
        count: Number of cheapest hours to return (default 3)
    
    Returns:
        Human-readable string with recommendations.
    """
    fc = forecast(hours=48)
    
    # Sort by price and take cheapest
    sorted_fc = sorted(fc, key=lambda x: x["price_ct"])
    best = sorted_fc[:count]
    
    if not best:
        return "Keine Prognose verfügbar."
    
    lines = [f"Günstigste {count} Stunden in den nächsten 48h:"]
    for b in sorted(best, key=lambda x: x["timestamp"]):
        lines.append(
            f"  {b['timestamp'][11:16]} → {b['price_ct']} ct/kWh "
            f"(Konfidenz: {b['confidence']:.0%})"
        )
    
    # Calculate average
    avg = sum(b["price_ct"] for b in best) / len(best)
    lines.append(f"Ø {avg:.1f} ct/kWh")
    lines.append("")
    lines.append("Tipp:")
    lines.append("  Waschmaschine/Trockner/Spüler in diesem Fenster laufen lassen.")
    lines.append("  Wallbox auf diese Zeit programmieren (wenn dynamischer Tarif).")
    
    return "\n".join(lines)
