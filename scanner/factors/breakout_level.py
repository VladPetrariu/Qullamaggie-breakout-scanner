"""Section D — Breakout level significance.

Classifies where price is breaking out relative to historical levels:
1. All-time high     — no overhead supply, price discovery, maximum conviction
2. Multi-year high   — minimal supply, long-term resistance flipping (2-5yr)
3. 52-week high      — solid, some overhead
4. Prior resistance  — weakest, needs compensation from other factors

With yfinance period="1y" we get ~250 days. ATH and multi-year detection
use the available data range — if the 52wk high IS the data high, we
label it as ATH (best approximation without longer history).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import ATR_PERIOD


def compute_breakout_level(ticker: str, df: pd.DataFrame) -> dict | None:
    """Classify breakout level significance for a single stock.

    Returns None if insufficient data.
    """
    if len(df) < 60:
        return None

    close = df["Close"]
    high = df["High"]
    current = close.iloc[-1]

    data_high = high.max()
    high_52wk = high.tail(252).max() if len(high) >= 252 else high.max()

    # Distance from current price to the data high (as % of price)
    pct_from_high = round(float((data_high - current) / current * 100), 2)

    # ATR for threshold calibration
    atr = _atr_last(df)
    if atr is None or atr <= 0:
        return None

    # Distance in ATR units
    atr_from_high = (data_high - current) / atr

    # ── Classification ────────────────────────────────────
    level_type, level_value = _classify_level(df, current, data_high, high_52wk, atr)

    # Distance from current close to the classified level
    dist_to_level = round(float((level_value - current) / atr), 2) if level_value else None

    return {
        "level_type": level_type,
        "level_label": _LEVEL_LABELS.get(level_type, level_type),
        "level_value": round(float(level_value), 2) if level_value else None,
        "pct_from_high": pct_from_high,
        "atr_from_level": dist_to_level,
    }


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------

_LEVEL_LABELS = {
    "ath": "ATH",
    "multi_year": "Multi-Year",
    "52wk": "52wk High",
    "prior_resistance": "Prior Resist.",
}


def _classify_level(
    df: pd.DataFrame,
    current: float,
    data_high: float,
    high_52wk: float,
    atr: float,
) -> tuple[str, float]:
    """Determine which type of level the stock is near or breaking out of."""
    high = df["High"]

    # Within 1 ATR of the all-time (data) high → ATH breakout territory
    if current >= data_high - atr:
        return "ath", data_high

    # If we have >252 days of data, check for multi-year high
    if len(high) > 252:
        older_high = high.iloc[:-252].max()
        if not pd.isna(older_high) and current >= older_high - atr:
            return "multi_year", older_high

    # Within 1 ATR of the 52-week high
    if current >= high_52wk - atr:
        return "52wk", high_52wk

    # Otherwise, find the nearest prior resistance level
    resistance = _find_prior_resistance(df, current, atr)
    return "prior_resistance", resistance


def _find_prior_resistance(
    df: pd.DataFrame,
    current: float,
    atr: float,
) -> float:
    """Find the nearest overhead resistance from recent price action.

    Looks for price levels where multiple highs cluster (supply zones).
    Falls back to the 20-day high if no clear cluster is found.
    """
    high = df["High"]

    # Simple approach: find the highest high in a sliding 5-day window
    # where price reversed down, indicating resistance
    rolling_high = high.rolling(5).max()
    # Levels where price hit a high then pulled back
    resistance_levels = []

    for i in range(len(df) - 30, len(df) - 5):
        if i < 0:
            continue
        local_high = rolling_high.iloc[i]
        if pd.isna(local_high):
            continue
        # Did price pull back after this high?
        next_5_close = df["Close"].iloc[i + 1:i + 6].min()
        if next_5_close < local_high * 0.98:  # at least 2% pullback
            resistance_levels.append(local_high)

    if resistance_levels:
        # Find the nearest overhead level
        overhead = [r for r in resistance_levels if r >= current]
        if overhead:
            return min(overhead)

    # Fallback: 20-day high
    return float(high.tail(20).max())


def _atr_last(df: pd.DataFrame, period: int = ATR_PERIOD) -> float | None:
    """Get the most recent ATR value."""
    if len(df) < period + 1:
        return None

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    val = tr.rolling(period).mean().iloc[-1]
    return float(val) if pd.notna(val) else None
