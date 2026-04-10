"""Stock profile — float, short interest, 21-day ABR, sector.

ABR is computed from existing price data (fast).
Float/SI/sector are fetched from yfinance Ticker.info (slow, cached 30 days).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yfinance as yf
from tqdm import tqdm

from .cache import Cache
from .config import ABR_PERIOD

# How many top stocks to enrich with yfinance profile data
PROFILE_FETCH_LIMIT = 50
PROFILE_CACHE_TTL_HOURS = 30 * 24  # 30 days


def compute_abr(df: pd.DataFrame, period: int = ABR_PERIOD) -> float | None:
    """21-day Average Body Range — bodies only, gaps excluded.

    ABR = mean(|Close - Open|) over the last *period* days.
    Used to normalise distances and position sizing.
    """
    if len(df) < period:
        return None
    body = (df["Close"] - df["Open"]).abs().tail(period)
    val = body.mean()
    return round(val, 4) if pd.notna(val) else None


def compute_abr_universe(
    universe: list[str], price_data: dict[str, pd.DataFrame]
) -> dict[str, float]:
    """Compute ABR for every stock in the universe (fast — no API calls)."""
    result: dict[str, float] = {}
    for ticker in universe:
        df = price_data.get(ticker)
        if df is None:
            continue
        abr = compute_abr(df)
        if abr is not None:
            result[ticker] = abr
    return result


def fetch_stock_profiles(
    tickers: list[str],
    cache: Cache,
    limit: int = PROFILE_FETCH_LIMIT,
) -> dict[str, dict]:
    """Fetch float, short interest, and sector from yfinance.

    Only fetches the first *limit* tickers that aren't already cached.
    Cached for 30 days since these fields change slowly.
    """
    cached = cache.get_json("profiles", max_age_hours=PROFILE_CACHE_TTL_HOURS)
    profiles: dict[str, dict] = cached if cached else {}

    to_fetch = [t for t in tickers[:limit] if t not in profiles]
    if not to_fetch:
        return profiles

    for ticker in tqdm(to_fetch, desc="  Fetching profiles", unit="stock"):
        try:
            info = yf.Ticker(ticker).info or {}
            float_shares = info.get("floatShares")
            profiles[ticker] = {
                "float_shares": float_shares,
                "float_label": _float_label(float_shares),
                "short_pct_float": info.get("shortPercentOfFloat"),
                "short_ratio": info.get("shortRatio"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
            }
        except Exception:
            profiles[ticker] = {}

    cache.set_json("profiles", profiles)
    return profiles


def _float_label(shares: int | None) -> str:
    if shares is None:
        return "unknown"
    millions = shares / 1_000_000
    if millions < 10:
        return "micro"
    if millions < 50:
        return "small"
    if millions < 100:
        return "medium"
    return "large"
