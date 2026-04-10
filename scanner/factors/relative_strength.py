"""Section C — Relative strength (ATR-normalized vs full universe).

C1. RS direction   — 5-day change in percentile (most actionable)
C2. Absolute percentile — rank vs full universe
C3. vs benchmark   — outperformance vs SPY (sector ETF added later)
"""

import pandas as pd
import numpy as np

from ..config import SECTOR_ETFS


def compute_universe_rs(
    price_data: dict[str, pd.DataFrame],
    universe: list[str],
) -> dict[str, dict]:
    """Compute ATR-normalized relative strength for every stock in the universe.

    Returns {ticker: {rs_percentile, rs_direction, rs_direction_label,
    vs_spy, vs_spy_label}}.
    """
    rs_now: dict[str, float] = {}
    rs_5d: dict[str, float] = {}
    ret_now: dict[str, float] = {}

    for ticker in universe:
        df = price_data.get(ticker)
        if df is None or len(df) < 35:
            continue

        close = df["Close"]
        atr = _atr(df, 14)

        # RS score = 20-day return / (ATR / price)
        # Equivalent to: (close - close_20d_ago) / ATR
        score_series = (close - close.shift(20)) / atr
        score_series = score_series.replace([np.inf, -np.inf], np.nan)

        if pd.notna(score_series.iloc[-1]):
            rs_now[ticker] = score_series.iloc[-1]
            ret_now[ticker] = close.pct_change(20).iloc[-1]

        if len(score_series) > 5 and pd.notna(score_series.iloc[-6]):
            rs_5d[ticker] = score_series.iloc[-6]

    # Rank → percentile (0-100)
    now_s = pd.Series(rs_now)
    pctile_now = now_s.rank(pct=True) * 100

    d5_s = pd.Series(rs_5d)
    pctile_5d = d5_s.rank(pct=True) * 100

    # SPY return for benchmark comparison
    spy_ret = _spy_return(price_data)

    results: dict[str, dict] = {}
    for ticker in universe:
        if ticker not in pctile_now:
            continue

        pct = pctile_now[ticker]
        pct_5d = pctile_5d.get(ticker, pct)
        direction = pct - pct_5d

        # vs SPY
        stock_ret = ret_now.get(ticker, 0)
        vs = (stock_ret - spy_ret) * 100 if spy_ret is not None else None

        results[ticker] = {
            "rs_percentile": round(pct, 1),
            "rs_direction": round(direction, 1),
            "rs_direction_label": _direction_label(direction),
            "vs_spy": round(vs, 1) if vs is not None else None,
            "vs_spy_label": _vs_label(vs),
        }

    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Average True Range."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def _spy_return(price_data):
    """Get SPY's 20-day return."""
    spy = price_data.get("SPY")
    if spy is None or len(spy) < 21:
        return None
    return spy["Close"].pct_change(20).iloc[-1]


def compute_sector_etf_returns(
    price_data: dict[str, pd.DataFrame],
) -> dict[str, float]:
    """Compute 20-day return for each sector ETF.

    Returns {sector_name: 20d_return}.
    """
    results: dict[str, float] = {}
    for sector, etf in SECTOR_ETFS.items():
        df = price_data.get(etf)
        if df is None or len(df) < 21:
            continue
        ret = df["Close"].pct_change(20).iloc[-1]
        if pd.notna(ret):
            results[sector] = float(ret)
    return results


def _direction_label(direction: float) -> str:
    if direction >= 10:
        return "surging"
    if direction >= 3:
        return "rising"
    if direction <= -10:
        return "collapsing"
    if direction <= -3:
        return "falling"
    return "flat"


def _vs_label(vs: float | None) -> str:
    if vs is None:
        return "unknown"
    if vs >= 10:
        return "leading"
    if vs >= -5:
        return "neutral"
    return "laggard"
