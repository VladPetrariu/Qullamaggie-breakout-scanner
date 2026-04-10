"""Watchlist ranking — full 3-tier sort (from flowchart).

Primary:    Catalyst presence + freshness score
Secondary:  Factor quality count (how many factors are strong)
Tertiary:   ABR distance to breakout level (closer = higher)
"""

from __future__ import annotations


def rank_watchlist(watchlist: list[dict]) -> list[dict]:
    """Sort the watchlist by the 3-tier ranking system."""
    return sorted(watchlist, key=_sort_key)


def _sort_key(s: dict) -> tuple:
    """Return a sort tuple (lower = better for all components)."""
    # ── Primary: catalyst freshness (higher = better → negate) ──
    freshness = s.get("freshness_score", 0) or 0

    # ── Secondary: factor quality count (more strong factors = better) ──
    quality = _count_strong_factors(s)

    # ── Tertiary: ABR distance to breakout level (closer = better) ──
    abr_dist = s.get("abr_dist_to_level")
    if abr_dist is None:
        abr_dist = 999

    return (-freshness, -quality, abr_dist)


def _count_strong_factors(s: dict) -> int:
    """Count how many factors are in their 'strong' range.

    Each factor contributes 0 or 1. More strong factors = higher quality setup.
    """
    count = 0

    # EMA stack
    if s.get("ema_stack") in ("full", "partial"):
        count += 1

    # RS percentile
    if (s.get("rs_percentile") or 0) >= 70:
        count += 1

    # RS direction
    if (s.get("rs_direction") or 0) >= 3:
        count += 1

    # ATR compression (tight = good)
    if (s.get("atr_compression") or 999) <= 0.7:
        count += 1

    # Consolidation quality
    if (s.get("hh_hl_pct") or 0) >= 50:
        count += 1

    # Candle quality
    if s.get("candle_label") in ("ideal", "ok"):
        count += 1

    # Pole present
    if s.get("has_pole"):
        count += 1

    # Volume (last day vs 50-day avg)
    if (s.get("vol_ratio_50d") or 0) >= 1.5:
        count += 1

    # Flag volume dry-up
    if s.get("flag_vol_label") in ("dry_up", "contracting"):
        count += 1

    # Breakout level significance
    if s.get("level_type") in ("ath", "multi_year"):
        count += 1

    # Weekly confluence
    if s.get("weekly_confluence") in ("max_confluence", "max_confirmation", "strong"):
        count += 1

    return count
