"""Section E — Weekly chart confirmation.

Amplifies daily setup — daily is required, weekly adds confluence:
1. Weekly + daily coiling simultaneously  = maximum confluence
2. Weekly + daily breaking out simultaneously = maximum confirmation
3. Weekly tight + daily breaking out = strong
4. Weekly uptrend + daily flag = context only
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import EMA_PERIODS


def compute_weekly(ticker: str, df: pd.DataFrame) -> dict | None:
    """Compute weekly chart confirmation for a single stock.

    Resamples daily bars to weekly, then checks for coiling/breakout
    on the weekly timeframe.

    Returns None if insufficient data.
    """
    if len(df) < 60:
        return None

    # ── Resample to weekly bars ──────────────────────────────
    wk = _resample_weekly(df)
    if len(wk) < 12:
        return None

    # ── Weekly ATR compression (coiling) ─────────────────────
    wk_compression = _weekly_atr_compression(wk)
    wk_coiling = wk_compression <= 0.7

    # ── Weekly breakout detection ────────────────────────────
    wk_breaking_out = _weekly_breakout(wk)

    # ── Weekly trend (EMA stack) ─────────────────────────────
    wk_trend = _weekly_trend(wk)

    # ── Daily state (for confluence classification) ───────────
    daily_coiling = _daily_coiling(df)
    daily_breaking = _daily_breaking(df)

    # ── Confluence classification ─────────────────────────────
    confluence = _classify_confluence(
        wk_coiling, wk_breaking_out, wk_trend,
        daily_coiling, daily_breaking,
    )

    return {
        "weekly_compression": round(float(wk_compression), 2),
        "weekly_coiling": wk_coiling,
        "weekly_breaking_out": wk_breaking_out,
        "weekly_trend": wk_trend,
        "weekly_confluence": confluence,
        "weekly_confluence_label": _CONFLUENCE_LABELS.get(confluence, confluence),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONFLUENCE_LABELS = {
    "max_confluence": "Max Confluence",
    "max_confirmation": "Max Confirmation",
    "strong": "Strong",
    "context": "Context Only",
    "none": "None",
}


def _resample_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """Resample daily OHLCV to weekly bars."""
    wk = df.resample("W").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }).dropna()
    return wk


def _weekly_atr_compression(wk: pd.DataFrame) -> float:
    """ATR compression on weekly bars: short-term / longer-term."""
    close = wk["Close"]
    high = wk["High"]
    low = wk["Low"]

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    atr_3 = tr.rolling(3).mean().iloc[-1]
    atr_10 = tr.rolling(10).mean().iloc[-1]

    if pd.isna(atr_3) or pd.isna(atr_10) or atr_10 == 0:
        return 1.0

    return float(atr_3 / atr_10)


def _weekly_breakout(wk: pd.DataFrame) -> bool:
    """Check if the most recent weekly bar broke above the prior 4-week high."""
    if len(wk) < 5:
        return False

    prior_high = wk["High"].iloc[-5:-1].max()
    last_close = wk["Close"].iloc[-1]
    return bool(last_close > prior_high)


def _weekly_trend(wk: pd.DataFrame) -> str:
    """Classify weekly trend using 10/20 EMA stack."""
    if len(wk) < 20:
        return "unknown"

    close = wk["Close"]
    ema10 = close.ewm(span=10, adjust=False).mean().iloc[-1]
    ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
    price = close.iloc[-1]

    if price > ema10 > ema20:
        return "uptrend"
    if price > ema20:
        return "above_20"
    return "weak"


def _daily_coiling(df: pd.DataFrame) -> bool:
    """Check if daily chart is coiling (ATR compression <= 0.7)."""
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    atr_5 = tr.rolling(5).mean().iloc[-1]
    atr_20 = tr.rolling(20).mean().iloc[-1]

    if pd.isna(atr_5) or pd.isna(atr_20) or atr_20 == 0:
        return False

    return bool(atr_5 / atr_20 <= 0.7)


def _daily_breaking(df: pd.DataFrame) -> bool:
    """Check if the most recent daily bar broke above the prior 20-day high."""
    if len(df) < 21:
        return False

    prior_high = df["High"].iloc[-21:-1].max()
    last_close = df["Close"].iloc[-1]
    return bool(last_close > prior_high)


def _classify_confluence(
    wk_coiling: bool,
    wk_breaking: bool,
    wk_trend: str,
    daily_coiling: bool,
    daily_breaking: bool,
) -> str:
    """Classify the weekly/daily confluence level."""
    if wk_coiling and daily_coiling:
        return "max_confluence"
    if wk_breaking and daily_breaking:
        return "max_confirmation"
    if wk_coiling and daily_breaking:
        return "strong"
    if wk_trend == "uptrend" and daily_coiling:
        return "context"
    return "none"
