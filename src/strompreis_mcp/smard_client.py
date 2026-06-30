"""SMARD API client — fetch German electricity market data from Bundesnetzagentur."""

import json
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import HTTPError

SMARD_BASE = "https://www.smard.de/app"
FILTER_DAY_AHEAD = 122  # Strompreis day-ahead (DE-LB)
FILTER_WIND_OFFSHORE = 1223
FILTER_WIND_ONSHORE = 1224
FILTER_SOLAR = 1225
FILTER_LOAD = 1226
REGION = "DE-LU"

# Cache for price data
_cache_price: Optional[dict] = None
_cache_timestamp: int = 0
_CACHE_TTL = 300  # 5 minutes


def _request(url: str) -> dict:
    """Fetch JSON from SMARD API."""
    req = Request(url, headers={"User-Agent": "strompreis-mcp/0.1.0"})
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def get_available_timestamps(filter_id: int = FILTER_DAY_AHEAD,
                              resolution: str = "hour") -> list:
    """Get list of available timestamps for a given filter/resolution combo.
    
    Returns: list of epoch milliseconds timestamps.
    """
    url = f"{SMARD_BASE}/chart_data/{filter_id}/{REGION}/index_{resolution}.json"
    data = _request(url)
    return data.get("timestamps", [])


def get_price_data(timestamp_ms: int) -> list:
    """Fetch electricity prices for a specific timestamp block.
    
    Args:
        timestamp_ms: Epoch milliseconds timestamp (from get_available_timestamps)
    
    Returns:
        List of [timestamp_ms, price_eur_per_mwh] pairs.
        Price is in EUR/MWh (divide by 10 for ct/kWh).
        None values mean data not yet available.
    """
    url = (f"{SMARD_BASE}/chart_data/{FILTER_DAY_AHEAD}/{REGION}/"
           f"{FILTER_DAY_AHEAD}_{REGION}_hour_{timestamp_ms}.json")
    data = _request(url)
    return data.get("series", [])


def get_latest_price_timestamp() -> int:
    """Get the most recent available timestamp for price data."""
    timestamps = get_available_timestamps()
    return max(timestamps) if timestamps else 0


def get_latest_prices() -> list:
    """Fetch the most recent price data block.
    
    Returns:
        List of [timestamp_ms, price_eur_per_mwh] sorted by time.
        Only returns entries with non-None values.
    """
    global _cache_price, _cache_timestamp
    
    now = int(time.time())
    if _cache_price and (now - _cache_timestamp) < _CACHE_TTL:
        return _cache_price
    
    ts = get_latest_price_timestamp()
    if not ts:
        return []
    
    series = get_price_data(ts)
    # Filter out None values and sort
    prices = [(t, v) for t, v in series if v is not None]
    prices.sort(key=lambda x: x[0])
    
    _cache_price = prices
    _cache_timestamp = now
    return prices


def get_generation_data(timestamp_ms: int, filter_id: int) -> list:
    """Fetch generation/load data for a specific timestamp.
    
    Args:
        timestamp_ms: Epoch milliseconds timestamp
        filter_id: One of FILTER_WIND_OFFSHORE, FILTER_WIND_ONSHORE, 
                   FILTER_SOLAR, FILTER_LOAD
    
    Returns:
        List of [timestamp_ms, value_mwh] pairs.
    """
    url = (f"{SMARD_BASE}/chart_data/{filter_id}/{REGION}/"
           f"{filter_id}_{REGION}_hour_{timestamp_ms}.json")
    try:
        data = _request(url)
        series = data.get("series", [])
        return [(t, v) for t, v in series if v is not None]
    except HTTPError:
        return []


def get_timeseries(days: int = 30) -> dict:
    """Get comprehensive time series data for modelling.
    
    Args:
        days: Number of days of historical data to fetch
    
    Returns:
        Dict with keys: 'prices', 'solar', 'wind', 'load'
        Each is a list of [timestamp_ms, value] sorted by time.
    """
    timestamps = get_available_timestamps()
    if not timestamps:
        return {"prices": [], "solar": [], "wind": [], "load": []}
    
    # Get the two most recent timestamp blocks
    # (each covers ~7 days of hourly data = 168 entries)
    ts_blocks = sorted(timestamps)[-3:]  # Last 3 blocks = ~21 days
    
    result = {
        "prices": [],
        "solar": [],
        "wind": [],
        "load": [],
    }
    
    for block_ts in ts_blocks:
        result["prices"].extend(get_price_data(block_ts))
    
    # Get generation data for the latest block
    if ts_blocks:
        latest = ts_blocks[-1]
        result["solar"] = get_generation_data(latest, FILTER_SOLAR)
        result["wind"] = (
            get_generation_data(latest, FILTER_WIND_ONSHORE) +
            get_generation_data(latest, FILTER_WIND_OFFSHORE)
        )
        result["load"] = get_generation_data(latest, FILTER_LOAD)
    
    # Sort and filter
    for key in result:
        result[key] = [(t, v) for t, v in result[key] if v is not None]
        result[key].sort(key=lambda x: x[0])
    
    return result
