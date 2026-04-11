"""Watchlist ranking — evidence-based sort (Phase 6 overhaul).

Primary:    ATR compression (tighter base = better, +3.05% quintile spread)
Secondary:  Factor quality count (adjusted — anti-predictive factors removed)
Tertiary:   ABR distance to breakout level (closer = higher)

Penalties applied before sorting:
- Post-catalyst cooldown: fresh catalyst + loose ATR = still extended
- Extension penalty: stock >2 ABR above breakout level

Based on walk-forward backtest results (Oct 2025 — Mar 2026, 2,400 picks).
See test_results/2026-04-10.md for full quintile analysis.
"""

from __future__ import annotations


def rank_watchlist(watchlist: list[dict]) -> list[dict]:
    """Sort the watchlist by evidence-based ranking."""
    return sorted(watchlist, key=_sort_key)


def _sort_key(s: dict) -> tuple:
    """Return a sort tuple (lower = better for all components).

    Two-tier approach:
    1. Quality gate — stocks without basic uptrend characteristics sort last.
       ATR compression alone can't distinguish "tight base" from "dead stock".
    2. Within quality-gated stocks, sort by ATR compression → quality → ABR.
    """
    # ── Quality gate ──
    # Stocks must show an uptrend to benefit from tight-ATR ranking.
    # Without this, dead/weak stocks with zero volatility rank first.
    has_uptrend = s.get("ema_stack") in ("full", "partial", "weak")
    has_min_rs = (s.get("rs_percentile") or 0) >= 20
    has_volume = (s.get("vol_ratio_50d") or 0) >= 0.1
    passes_gate = has_uptrend and has_min_rs and has_volume

    # Gate value: 0 = passes (sorts first), 1 = fails (sorts last)
    gate = 0 if passes_gate else 1

    # ── Primary: ATR compression (lower = tighter base = better) ──
    atr = s.get("atr_compression")
    if atr is None:
        atr = 999

    # ── Secondary: factor quality count (more strong factors = better) ──
    quality = _count_strong_factors(s)

    # ── Penalties ──
    penalty = _compute_penalties(s, atr)

    # ── Tertiary: ABR distance to breakout level (closer = better) ──
    abr_dist = s.get("abr_dist_to_level")
    if abr_dist is None:
        abr_dist = 999

    return (gate, atr, -(quality - penalty), abr_dist)


def _compute_penalties(s: dict, atr: float) -> int:
    """Compute ranking penalties based on backtest evidence.

    Returns a positive integer subtracted from the quality count.
    """
    penalty = 0

    # ── Post-catalyst cooldown (Step 35) ──
    # Fresh catalyst + ATR not yet compressed = stock still extended after move.
    # Backtest: freshest catalysts average -3.52% at 5d. Require consolidation
    # (low ATR compression) before promoting a stock with a recent catalyst.
    catalyst_age = s.get("catalyst_age")
    if catalyst_age is not None and catalyst_age <= 5 and atr > 0.8:
        penalty += 2

    # ── Extension penalty (Step 36) ──
    # Stocks trading >2 ABR above their breakout level tend to mean-revert.
    # Backtest: high volume ratio (proxy for extension) has -4.78% spread.
    abr_dist = s.get("abr_dist_to_level")
    if abr_dist is not None and abr_dist < -2.0:
        penalty += 1

    return penalty


def _count_strong_factors(s: dict) -> int:
    """Count how many factors are in their 'strong' range.

    Each factor contributes 0 or 1. More strong factors = higher quality setup.

    Removed (anti-predictive per backtest):
    - vol_ratio_50d >= 1.5 (high volume ratio: -4.78% quintile spread)
    """
    count = 0

    # EMA stack
    if s.get("ema_stack") in ("full", "partial"):
        count += 1

    # RS percentile (+0.42% spread — weak but directionally correct)
    if (s.get("rs_percentile") or 0) >= 70:
        count += 1

    # RS direction
    if (s.get("rs_direction") or 0) >= 3:
        count += 1

    # ATR compression (tight = good, +3.05% spread — strongest signal)
    if (s.get("atr_compression") or 999) <= 0.7:
        count += 1

    # Consolidation quality (+0.90% spread)
    if (s.get("hh_hl_pct") or 0) >= 50:
        count += 1

    # Candle quality
    if s.get("candle_label") in ("ideal", "ok"):
        count += 1

    # Pole present
    if s.get("has_pole"):
        count += 1

    # Flag volume dry-up (sign of consolidation — good)
    if s.get("flag_vol_label") in ("dry_up", "contracting"):
        count += 1

    # Breakout level significance
    if s.get("level_type") in ("ath", "multi_year"):
        count += 1

    # Weekly confluence
    if s.get("weekly_confluence") in ("max_confluence", "max_confirmation", "strong"):
        count += 1

    return count
