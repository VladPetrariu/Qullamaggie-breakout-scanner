"""Section B — Breakout volume + entry quality.

B1. Volume pace    — daily volume vs 50-day average (proxy for intraday pace)
B2. ABR distance   — distance from current close to breakout level in ABR units
B3. Flag volume    — volume contraction during consolidation flag
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import ABR_PERIOD


def compute_volume(ticker: str, df: pd.DataFrame) -> dict | None:
    """Compute all Section B factors for a single stock.

    Returns None if insufficient data.
    """
    if len(df) < 60:
        return None

    volume = df["Volume"]
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    open_ = df["Open"]

    # ── B1. Volume pace ──────────────────────────────────────
    avg_50 = volume.rolling(50).mean().iloc[-1]
    last_vol = volume.iloc[-1]

    if pd.isna(avg_50) or avg_50 <= 0:
        vol_ratio = None
        vol_label = "unknown"
    else:
        vol_ratio = round(float(last_vol / avg_50), 2)
        vol_label = _vol_label(vol_ratio)

    # ── B2. ABR distance to breakout level ───────────────────
    body = (close - open_).abs().tail(ABR_PERIOD)
    abr = body.mean()
    breakout_level = _estimate_breakout_level(df)

    if pd.isna(abr) or abr <= 0 or breakout_level is None:
        abr_dist = None
        abr_dist_label = "unknown"
    else:
        abr_dist = round(float((breakout_level - close.iloc[-1]) / abr), 2)
        abr_dist_label = _abr_dist_label(abr_dist)

    # ── B3. Flag volume pattern ──────────────────────────────
    flag_vol_ratio, flag_vol_label = _flag_volume(df)

    return {
        "vol_ratio_50d": vol_ratio,
        "vol_label": vol_label,
        "breakout_level": round(float(breakout_level), 2) if breakout_level is not None else None,
        "abr_dist_to_level": abr_dist,
        "abr_dist_label": abr_dist_label,
        "flag_vol_ratio": flag_vol_ratio,
        "flag_vol_label": flag_vol_label,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _vol_label(ratio: float) -> str:
    """Classify volume pace relative to 50-day average."""
    if ratio >= 5.0:
        return "extreme"
    if ratio >= 3.0:
        return "strong"
    if ratio >= 1.5:
        return "above_avg"
    if ratio >= 0.8:
        return "normal"
    return "quiet"


def _estimate_breakout_level(df: pd.DataFrame) -> float | None:
    """Estimate the nearest overhead resistance level.

    Uses the highest high in the recent consolidation range as a simple
    breakout level. More sophisticated level detection is in breakout_level.py.
    """
    if len(df) < 20:
        return None

    # Recent range: last 20 days high = resistance
    recent_high = df["High"].tail(20).max()
    if pd.isna(recent_high):
        return None
    return float(recent_high)


def _abr_dist_label(dist: float) -> str:
    """Classify distance to breakout level in ABR units.

    Positive = below level (room to run), negative = above level (extended).
    """
    if dist <= -1.5:
        return "extended"
    if dist < 0:
        return "above_level"
    if dist <= 0.2:
        return "at_level"
    if dist <= 0.5:
        return "near"
    if dist <= 1.0:
        return "acceptable"
    return "far"


def _flag_volume(df: pd.DataFrame) -> tuple[float | None, str]:
    """Detect volume contraction during consolidation flag.

    Compares average volume in the last 5 days (flag) vs the 5 days
    before that (pole/prior period). Low flag volume = ideal pattern.
    """
    if len(df) < 15:
        return None, "unknown"

    vol = df["Volume"]
    flag_avg = vol.tail(5).mean()
    prior_avg = vol.iloc[-10:-5].mean()

    if pd.isna(flag_avg) or pd.isna(prior_avg) or prior_avg <= 0:
        return None, "unknown"

    ratio = round(float(flag_avg / prior_avg), 2)

    if ratio < 0.5:
        label = "dry_up"      # ideal — volume drying up during flag
    elif ratio < 0.75:
        label = "contracting"  # good — volume declining
    elif ratio <= 1.0:
        label = "steady"       # neutral
    else:
        label = "elevated"     # interest maintained, not ideal for flag

    return ratio, label
