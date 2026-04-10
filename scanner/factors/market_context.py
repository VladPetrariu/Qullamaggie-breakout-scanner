"""Market context gate — overrides everything in crisis.

Computes five breadth indicators across the stock universe and classifies
the current market regime as favorable / mixed / caution / risk_off.
"""

import pandas as pd
import numpy as np

from ..config import MARKET_CONTEXT_THRESHOLDS


def compute_market_context(
    price_data: dict[str, pd.DataFrame],
    universe: list[str],
) -> dict:
    """Compute market-wide breadth indicators and classify regime.

    Parameters
    ----------
    price_data : full price data dict (includes ^VIX, SPY, etc.)
    universe : filtered list of stock tickers (no ETFs/benchmarks)

    Returns
    -------
    dict with keys: regime, pct_above_50ma, pct_above_20ma,
    highs_lows_ratio, new_highs, new_lows, vix_level, vix_direction,
    breakout_followthrough, indicator_regimes
    """
    pct_50 = _pct_above_ma(universe, price_data, 50)
    pct_20 = _pct_above_ma(universe, price_data, 20)
    new_highs, new_lows, hl_ratio = _highs_lows(universe, price_data)
    vix_level, vix_dir = _vix(price_data)
    followthrough = _breakout_followthrough(universe, price_data)

    # Classify each indicator
    ind = {}
    ind["pct_above_50ma"] = _classify(
        pct_50, MARKET_CONTEXT_THRESHOLDS["pct_above_50ma"]
    )
    ind["pct_above_20ma"] = _classify(
        pct_20, MARKET_CONTEXT_THRESHOLDS["pct_above_20ma"]
    )
    ind["highs_lows_ratio"] = _classify(
        hl_ratio, MARKET_CONTEXT_THRESHOLDS["highs_lows_ratio"]
    )
    ind["vix_level"] = _classify_vix(
        vix_level, MARKET_CONTEXT_THRESHOLDS["vix_level"]
    )

    # Overall regime = most bearish indicator (conservative)
    regime_order = ["risk_off", "caution", "mixed", "favorable"]
    regime = max(
        regime_order.index(r) for r in ind.values()
    )
    overall = regime_order[regime]

    # Override: if VIX is risk_off, overall is risk_off
    if ind["vix_level"] == "risk_off":
        overall = "risk_off"

    # Override: if majority are caution or worse, don't allow favorable
    bearish_count = sum(1 for r in ind.values() if r in ("caution", "risk_off"))
    if bearish_count >= 2 and overall == "favorable":
        overall = "mixed"

    return {
        "regime": overall,
        "pct_above_50ma": round(pct_50, 1),
        "pct_above_20ma": round(pct_20, 1),
        "highs_lows_ratio": round(hl_ratio, 2),
        "new_highs": new_highs,
        "new_lows": new_lows,
        "vix_level": round(vix_level, 2) if vix_level else None,
        "vix_direction": vix_dir,
        "breakout_followthrough": round(followthrough, 1),
        "indicator_regimes": ind,
    }


# ---------------------------------------------------------------------------
# Individual indicators
# ---------------------------------------------------------------------------


def _pct_above_ma(universe, price_data, period):
    """% of stocks whose last close is above their N-day simple MA."""
    above = 0
    total = 0
    for ticker in universe:
        df = price_data.get(ticker)
        if df is None or len(df) < period:
            continue
        ma = df["Close"].rolling(period).mean().iloc[-1]
        if pd.notna(ma):
            total += 1
            if df["Close"].iloc[-1] > ma:
                above += 1
    return (above / total * 100) if total else 0


def _highs_lows(universe, price_data):
    """Count stocks at 52-week high vs 52-week low (using last trading day)."""
    new_highs = 0
    new_lows = 0
    for ticker in universe:
        df = price_data.get(ticker)
        if df is None or len(df) < 200:
            continue
        last_close = df["Close"].iloc[-1]
        high_52 = df["High"].max()
        low_52 = df["Low"].min()
        # Within 2% of 52-week high/low counts as "at" the level
        if last_close >= high_52 * 0.98:
            new_highs += 1
        elif last_close <= low_52 * 1.02:
            new_lows += 1

    ratio = (new_highs / new_lows) if new_lows > 0 else float(new_highs)
    return new_highs, new_lows, ratio


def _vix(price_data):
    """Get current VIX level and 5-day direction."""
    vix_df = price_data.get("^VIX")
    if vix_df is None or len(vix_df) < 6:
        return None, "unknown"

    level = vix_df["Close"].iloc[-1]
    level_5d = vix_df["Close"].iloc[-6]
    diff = level - level_5d

    if diff > 2:
        direction = "rising"
    elif diff < -2:
        direction = "falling"
    else:
        direction = "flat"

    return level, direction


def _breakout_followthrough(universe, price_data):
    """% of stocks that made 52-week highs 5 days ago and still hold gains.

    Measures whether breakouts are actually following through — a sign of
    healthy market momentum.
    """
    broke_out = 0
    held = 0
    for ticker in universe:
        df = price_data.get(ticker)
        if df is None or len(df) < 200:
            continue
        # Was the stock at a 52-week high 5 days ago?
        close_5d = df["Close"].iloc[-6]
        history_before = df.iloc[:-5]
        if len(history_before) < 100:
            continue
        high_52_then = history_before["High"].max()
        if close_5d >= high_52_then * 0.98:
            broke_out += 1
            # Is it still above that level?
            if df["Close"].iloc[-1] >= close_5d * 0.98:
                held += 1

    return (held / broke_out * 100) if broke_out else 0


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------


def _classify(value, thresholds):
    """Classify a higher-is-better indicator into a regime."""
    if value >= thresholds["favorable"]:
        return "favorable"
    elif value >= thresholds["mixed"]:
        return "mixed"
    elif value >= thresholds["caution"]:
        return "caution"
    return "risk_off"


def _classify_vix(value, thresholds):
    """Classify VIX (lower is better)."""
    if value is None:
        return "mixed"
    if value >= thresholds["risk_off"]:
        return "risk_off"
    if value >= thresholds["caution"]:
        return "caution"
    if value <= thresholds["favorable"]:
        return "favorable"
    return "mixed"
