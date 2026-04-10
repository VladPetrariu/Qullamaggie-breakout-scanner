"""Stock profile — float, short interest, 21-day ABR, sector.

ABR is computed from existing price data (fast).
Float/SI/sector are fetched from yfinance Ticker.info (slow, cached 30 days).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

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

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_one, t): t for t in to_fetch}
        with tqdm(total=len(to_fetch), desc="  Fetching profiles", unit="stock") as pbar:
            for fut in as_completed(futures):
                ticker = futures[fut]
                profiles[ticker] = fut.result()
                pbar.update(1)

    cache.set_json("profiles", profiles)
    return profiles


def _fetch_one(ticker: str) -> dict:
    """Fetch profile data + earnings dates for a single ticker."""
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        float_shares = info.get("floatShares")

        # Earnings dates — most recent past and next upcoming
        earnings = _parse_earnings(t)

        return {
            "float_shares": float_shares,
            "float_label": _float_label(float_shares),
            "short_pct_float": info.get("shortPercentOfFloat"),
            "short_ratio": info.get("shortRatio"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            **earnings,
        }
    except Exception:
        return {}


def _parse_earnings(t: yf.Ticker) -> dict:
    """Extract next upcoming earnings date from yfinance calendar."""
    try:
        cal = t.calendar
        if not cal or "Earnings Date" not in cal:
            return {"next_earnings": None, "earnings_days_ago": None}

        dates = cal["Earnings Date"]
        if not dates:
            return {"next_earnings": None, "earnings_days_ago": None}

        # calendar returns a list of dates (usually 1-2)
        import datetime
        today = datetime.date.today()

        # Find next future and most recent past earnings
        next_dt = None
        last_dt = None
        for d in (dates if isinstance(dates, list) else [dates]):
            if isinstance(d, datetime.datetime):
                d = d.date()
            if d >= today and (next_dt is None or d < next_dt):
                next_dt = d
            if d < today and (last_dt is None or d > last_dt):
                last_dt = d

        days_ago = (today - last_dt).days if last_dt is not None else None

        return {
            "next_earnings": str(next_dt) if next_dt else None,
            "earnings_days_ago": days_ago,
        }
    except Exception:
        return {"next_earnings": None, "earnings_days_ago": None}


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
