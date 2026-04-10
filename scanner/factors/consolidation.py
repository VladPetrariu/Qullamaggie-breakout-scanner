"""Section A — Consolidation quality.

A1. Price structure  — HH/HL days, slope of lows
A2. Candle quality   — body/wick ratio
A3. EMA interaction  — distance to 10/20/50 EMA, stack order
A4. Momentum pattern — pole+flag detection
A5. Duration         — how long the consolidation has lasted
"""

import pandas as pd
import numpy as np

from ..config import (
    CANDLE_QUALITY_BARCODE,
    CANDLE_QUALITY_IDEAL,
    CANDLE_QUALITY_OK,
    CONSOLIDATION_MAX_DAYS,
    CONSOLIDATION_MIN_DAYS,
    EMA_PERIODS,
)


def compute_consolidation(ticker: str, df: pd.DataFrame) -> dict | None:
    """Compute all Section A factors for a single stock.

    Returns None if there is insufficient data.
    """
    if len(df) < 60:
        return None

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    open_ = df["Open"]

    # ── A3. EMA interaction ───────────────────────────────────
    emas = {}
    ema_dists = {}
    for p in EMA_PERIODS:
        ema = close.ewm(span=p, adjust=False).mean()
        emas[p] = ema
        ema_dists[p] = round((close.iloc[-1] - ema.iloc[-1]) / close.iloc[-1] * 100, 2)

    last_close = close.iloc[-1]
    stack = _ema_stack(last_close, emas)
    closest_ema = min(EMA_PERIODS, key=lambda p: abs(ema_dists[p]))

    # ── Detect consolidation period ───────────────────────────
    consol_start = _find_consolidation_start(df)
    consol_days = len(df) - consol_start
    consol_days = min(consol_days, CONSOLIDATION_MAX_DAYS)
    consol_slice = df.iloc[consol_start:]

    # ── A5. Duration ──────────────────────────────────────────
    duration_label = _duration_label(consol_days)

    # ── A1. Price structure ───────────────────────────────────
    hh_hl_pct, slope_of_lows = _price_structure(consol_slice)

    # ── A2. Candle quality ────────────────────────────────────
    candle_q, candle_label = _candle_quality(consol_slice)

    # ── A4. Momentum (pole detection) ─────────────────────────
    pole_magnitude, has_pole = _detect_pole(df, consol_start)

    # ── ATR compression ───────────────────────────────────────
    atr_compression = _atr_compression(df)

    return {
        "ema_10_dist": ema_dists[10],
        "ema_20_dist": ema_dists[20],
        "ema_50_dist": ema_dists[50],
        "ema_stack": stack,
        "closest_ema": closest_ema,
        "consol_days": consol_days,
        "consol_label": duration_label,
        "hh_hl_pct": round(hh_hl_pct, 1),
        "slope_of_lows": round(slope_of_lows, 4),
        "candle_quality": round(candle_q, 2),
        "candle_label": candle_label,
        "has_pole": has_pole,
        "pole_magnitude": round(pole_magnitude, 1),
        "atr_compression": round(atr_compression, 2),
    }


# ---------------------------------------------------------------------------
# Sub-factor helpers
# ---------------------------------------------------------------------------


def _ema_stack(price: float, emas: dict[int, pd.Series]) -> str:
    """Check EMA ordering: price > 10 > 20 > 50 = full stack."""
    e10 = emas[10].iloc[-1]
    e20 = emas[20].iloc[-1]
    e50 = emas[50].iloc[-1]

    if price > e10 > e20 > e50:
        return "full"
    if price > e20 > e50:
        return "partial"
    if price > e50:
        return "weak"
    return "none"


def _find_consolidation_start(df: pd.DataFrame) -> int:
    """Find where the current consolidation began.

    Looks for the most recent "big move" day (daily range > 2x ATR)
    and defines consolidation as starting the day after.
    """
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(14).mean()

    # Search backwards for a big-move day (range > 2x ATR)
    lookback = min(len(df) - 1, CONSOLIDATION_MAX_DAYS + 20)
    for i in range(len(df) - CONSOLIDATION_MIN_DAYS, len(df) - lookback, -1):
        if i < 0 or pd.isna(atr.iloc[i]):
            continue
        if tr.iloc[i] > 2.0 * atr.iloc[i]:
            return i + 1  # consolidation starts after the big move

    # No big move found — use a range-contraction heuristic:
    # consolidation starts where ATR peaked in the lookback window
    window = atr.iloc[-lookback:]
    if window.notna().any():
        peak_idx = window.idxmax()
        return df.index.get_loc(peak_idx) + 1

    return max(0, len(df) - 20)  # fallback: last 20 days


def _duration_label(days: int) -> str:
    if days < CONSOLIDATION_MIN_DAYS:
        return "too_short"
    if days <= 7:
        return "min"
    if days <= 14:
        return "good"
    if days <= 28:
        return "strong"
    if days <= 60:
        return "very_strong"
    return "powerful"


def _price_structure(consol: pd.DataFrame) -> tuple[float, float]:
    """A1: Compute % of days with higher-highs AND higher-lows,
    plus the slope of the lows (positive = rising).
    """
    if len(consol) < 2:
        return 0.0, 0.0

    highs = consol["High"].values
    lows = consol["Low"].values

    hh_hl_days = 0
    for i in range(1, len(consol)):
        if highs[i] >= highs[i - 1] and lows[i] >= lows[i - 1]:
            hh_hl_days += 1

    pct = hh_hl_days / (len(consol) - 1) * 100

    # Slope of lows: linear regression slope normalised by price
    x = np.arange(len(lows), dtype=float)
    if len(x) >= 2 and np.std(x) > 0:
        slope = np.polyfit(x, lows, 1)[0]
        slope_norm = slope / np.mean(lows)  # as fraction of price
    else:
        slope_norm = 0.0

    return pct, slope_norm


def _candle_quality(consol: pd.DataFrame) -> tuple[float, str]:
    """A2: Average body/range ratio during consolidation.

    High ratio = clean candles (bodies, not wicks).
    Low ratio = barcodes (all wick, wide risk).
    """
    body = (consol["Close"] - consol["Open"]).abs()
    full_range = consol["High"] - consol["Low"]

    # Avoid division by zero for doji candles
    ratio = body / full_range.replace(0, np.nan)
    avg = ratio.mean()

    if pd.isna(avg):
        return 0.0, "unknown"
    if avg >= CANDLE_QUALITY_IDEAL:
        label = "ideal"
    elif avg >= CANDLE_QUALITY_OK:
        label = "ok"
    elif avg >= CANDLE_QUALITY_BARCODE:
        label = "weak"
    else:
        label = "barcode"

    return avg, label


def _detect_pole(df: pd.DataFrame, consol_start: int) -> tuple[float, bool]:
    """A4: Check if there was a significant directional up-move (pole)
    before consolidation.

    Measures the close-to-close gain over the 20 days before consolidation
    started.  A directional gain of >= 20% counts as a pole.
    """
    pole_end = consol_start
    pole_begin = max(0, pole_end - 20)

    if pole_end - pole_begin < 3:
        return 0.0, False

    segment = df.iloc[pole_begin:pole_end]
    if len(segment) < 2:
        return 0.0, False

    start_price = segment["Close"].iloc[0]
    end_price = segment["Close"].iloc[-1]

    if start_price <= 0:
        return 0.0, False

    # Must be an upward move for a valid pole
    magnitude = (end_price - start_price) / start_price * 100
    if magnitude <= 0:
        return 0.0, False

    return round(float(magnitude), 1), bool(magnitude >= 20.0)


def _atr_compression(df: pd.DataFrame) -> float:
    """Ratio of short-term ATR to longer-term ATR. Values < 0.7 = tight."""
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr_5 = tr.rolling(5).mean().iloc[-1]
    atr_20 = tr.rolling(20).mean().iloc[-1]

    if pd.isna(atr_5) or pd.isna(atr_20) or atr_20 == 0:
        return 1.0

    return atr_5 / atr_20
