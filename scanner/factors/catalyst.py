"""Catalyst detection — volume spike proxy + freshness scoring.

Since yfinance doesn't provide news/8-K feeds, we detect catalysts via:
1. Volume spikes (>3x 20-day avg) as proxy for "something happened"
2. Spike magnitude determines tier (significance)
3. Freshness scoring: age half-life decay (0.40) + extension penalty (0.60)

Freshness bands (from flowchart):
  Early  0.75-1.00 — fresh catalyst, minimal price extension
  Active 0.50-0.75 — catalyst aging but move still developing
  Late   0.25-0.50 — most of the move likely done
  Dead   0.00-0.25 — catalyst exhausted
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import (
    CATALYST_HALFLIFE,
    EARNINGS_LOOKBACK_DAYS,
    FRESHNESS_AGE_WEIGHT,
    FRESHNESS_EXT_WEIGHT,
    VOLUME_SPIKE_THRESHOLD,
)


def compute_catalyst(ticker: str, df: pd.DataFrame) -> dict | None:
    """Detect catalyst events from volume spikes and compute freshness.

    Returns None if insufficient data.
    """
    if len(df) < 30:
        return None

    volume = df["Volume"]
    avg_vol = volume.rolling(20).mean()

    # Search the lookback window for volume spikes
    lookback = min(EARNINGS_LOOKBACK_DAYS, len(df) - 20)
    if lookback < 1:
        return None

    spikes = []
    for i in range(len(df) - lookback, len(df)):
        avg = avg_vol.iloc[i]
        if pd.isna(avg) or avg <= 0:
            continue

        ratio = volume.iloc[i] / avg
        if ratio >= VOLUME_SPIKE_THRESHOLD:
            age = len(df) - 1 - i  # trading days ago
            spikes.append({
                "age_days": age,
                "vol_ratio": round(float(ratio), 1),
                "tier": _spike_tier(ratio),
            })

    if not spikes:
        return {
            "has_catalyst": False,
            "catalyst_count": 0,
            "freshness_score": 0.0,
            "freshness_label": "none",
            "catalyst_age": None,
            "catalyst_vol_ratio": None,
            "catalyst_tier": None,
        }

    # Pick the best spike: highest freshness-weighted significance
    best = max(
        spikes,
        key=lambda s: _age_decay(s["age_days"], s["tier"]) * s["vol_ratio"],
    )

    # Freshness = age_decay * 0.40 + extension_score * 0.60
    age_score = _age_decay(best["age_days"], best["tier"])
    ext_score = _extension_score(df, best["age_days"])
    freshness = FRESHNESS_AGE_WEIGHT * age_score + FRESHNESS_EXT_WEIGHT * ext_score
    freshness = round(min(1.0, max(0.0, freshness)), 2)

    return {
        "has_catalyst": True,
        "catalyst_count": len(spikes),
        "freshness_score": freshness,
        "freshness_label": _freshness_label(freshness),
        "catalyst_age": best["age_days"],
        "catalyst_vol_ratio": best["vol_ratio"],
        "catalyst_tier": best["tier"],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spike_tier(vol_ratio: float) -> int:
    """Map volume spike magnitude to catalyst tier.

    Higher volume = more significant event = shorter halflife (decays faster
    but starts stronger).
    """
    if vol_ratio >= 8.0:
        return 1  # extreme — likely major news / earnings blowout
    if vol_ratio >= 5.0:
        return 2  # strong — likely earnings or significant event
    return 3      # moderate — sector rotation, smaller catalyst


def _age_decay(age_days: int, tier: int) -> float:
    """Exponential decay based on tier halflife."""
    halflife = CATALYST_HALFLIFE.get(f"tier{tier}", 10)
    return float(np.exp(-0.693 * age_days / halflife))


def _extension_score(df: pd.DataFrame, age_days: int) -> float:
    """How much room is left in the move since the catalyst.

    Measures price extension from catalyst day in ATR units.
    Less extension = higher score = more upside potential remaining.
    """
    if age_days <= 0 or age_days >= len(df):
        return 1.0

    close = df["Close"]
    catalyst_close = close.iloc[-(age_days + 1)]
    current_close = close.iloc[-1]

    # ATR for normalization
    high = df["High"]
    low = df["Low"]
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]

    if pd.isna(atr) or atr <= 0:
        return 0.5

    extension = abs(current_close - catalyst_close) / atr
    # Score: 1.0 at 0 ATR extension, 0.0 at 5+ ATR extension
    return max(0.0, 1.0 - extension / 5.0)


def _freshness_label(score: float) -> str:
    if score >= 0.75:
        return "early"
    if score >= 0.50:
        return "active"
    if score >= 0.25:
        return "late"
    return "dead"
