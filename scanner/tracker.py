"""Historical result tracker — measure post-scan outcomes.

Loads prior scan JSON files, looks up current prices, and computes
the return at 1/3/5/10 day horizons for each stock that appeared.
Aggregates into win rate and average return statistics.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from .config import SCANS_DIR


def compute_track_record(
    price_data: dict[str, pd.DataFrame],
    max_scans: int = 20,
) -> dict:
    """Compute historical outcomes for past scan watchlists.

    Returns a summary dict with:
      - per_horizon: {1: {win_rate, avg_return, n}, 3: ..., 5: ..., 10: ...}
      - recent_calls: list of {ticker, scan_date, returns: {1: x, 3: x, ...}}
    """
    scan_files = sorted(SCANS_DIR.glob("scan_*.json"), reverse=True)

    # Skip today's scan — we want completed horizons only
    today = datetime.now().strftime("%Y-%m-%d")
    past_scans = [f for f in scan_files if f.stem.replace("scan_", "") < today]

    if not past_scans:
        return {"per_horizon": {}, "recent_calls": [], "total_scans": 0}

    horizons = [1, 3, 5, 10]
    all_returns: dict[int, list[float]] = {h: [] for h in horizons}
    recent_calls: list[dict] = []

    for scan_path in past_scans[:max_scans]:
        scan_date_str = scan_path.stem.replace("scan_", "")
        try:
            scan_data = json.loads(scan_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        watchlist = scan_data.get("watchlist", [])
        # Only measure top 20 ranked stocks (the ones you'd actually trade)
        for stock in watchlist[:20]:
            ticker = stock["ticker"]
            df = price_data.get(ticker)
            if df is None or len(df) < 20:
                continue

            # Find the scan date in the price data
            scan_idx = _find_date_index(df, scan_date_str)
            if scan_idx is None:
                continue

            entry_price = df["Close"].iloc[scan_idx]
            if entry_price <= 0:
                continue

            returns = {}
            for h in horizons:
                target_idx = scan_idx + h
                if target_idx < len(df):
                    exit_price = df["Close"].iloc[target_idx]
                    ret = round((exit_price - entry_price) / entry_price * 100, 2)
                    returns[h] = ret
                    all_returns[h].append(ret)

            if returns:
                recent_calls.append({
                    "ticker": ticker,
                    "scan_date": scan_date_str,
                    "returns": returns,
                })

    # Aggregate statistics
    per_horizon = {}
    for h in horizons:
        vals = all_returns[h]
        if vals:
            per_horizon[h] = {
                "win_rate": round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1),
                "avg_return": round(sum(vals) / len(vals), 2),
                "n": len(vals),
            }

    return {
        "per_horizon": per_horizon,
        "recent_calls": recent_calls[-50:],  # last 50 entries
        "total_scans": len(past_scans[:max_scans]),
    }


def _find_date_index(df: pd.DataFrame, date_str: str) -> int | None:
    """Find the index position of a date in the DataFrame."""
    try:
        target = pd.Timestamp(date_str)
        # Find exact match or next trading day
        idx = df.index.searchsorted(target)
        if idx >= len(df):
            return None
        # Verify it's within 3 days (accounts for weekends)
        actual = df.index[idx]
        if abs((actual - target).days) > 3:
            return None
        return idx
    except (ValueError, KeyError):
        return None
