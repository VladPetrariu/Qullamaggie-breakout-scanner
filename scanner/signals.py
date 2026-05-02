"""Trade signal generator (Phase 10, step 51).

Converts the scanner's ranked watchlist into actionable trade signals:
entry price (the breakout level), stop price (entry - 3 × ATR), and
position size (1% account risk, capped at 20% account). Signals are
gated to favorable-regime days only — exit-strategy backtest (step 53b)
showed mixed/caution regimes have negative expectancy across every
exit policy.

The signals are intended for downstream consumption by the Alpaca
execution engine (step 52). This module never places orders itself.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date as dt_date
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .config import (
    ATR_PERIOD,
    DEFAULT_ACCOUNT_EQUITY,
    ENTRY_BUFFER_PCT,
    MAX_CONCURRENT_POSITIONS,
    MAX_ENTRY_OVERSHOOT_PCT,
    MAX_HOLD_DAYS,
    MAX_LEVEL_DISTANCE_PCT,
    MAX_POSITION_PCT,
    MIN_STOP_DISTANCE_PCT,
    RISK_PER_TRADE_PCT,
    SCANS_DIR,
    SIGNAL_TRADABLE_REGIMES,
    STOP_ATR_MULTIPLIER,
)


@dataclass
class Signal:
    """One actionable trade. All prices in dollars, sizes in shares."""

    ticker: str
    name: str
    rank: int

    # Pricing
    last_close: float
    breakout_level: float
    limit_entry: float          # actual limit order price (level + small buffer)
    stop_price: float
    atr_value: float
    stop_distance_pct: float    # (entry - stop) / entry × 100

    # Sizing
    risk_dollars: float         # account_equity × risk_pct
    shares: int
    position_dollars: float
    position_pct_of_account: float

    # Context
    regime: str
    level_type: str             # "ath", "multi_year", "52wk", "prior_resistance"
    sector: str

    # Execution metadata
    max_hold_days: int
    generated_at: str           # ISO timestamp
    notes: list[str] = field(default_factory=list)


# ── ATR helper (Wilder, matches exit-strategy backtest) ──────────────────


def _wilder_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> float | None:
    """ATR using Wilder's smoothing. Returns last value or None if insufficient data."""
    if len(df) < period + 1:
        return None
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift()
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    val = tr.ewm(alpha=1 / period, adjust=False).mean().iloc[-1]
    return float(val) if pd.notna(val) and val > 0 else None


# ── Per-stock signal computation ─────────────────────────────────────────


def _build_signal(
    stock: dict,
    df: pd.DataFrame,
    regime: str,
    account_equity: float,
    rank: int,
) -> Signal | None:
    """Build a Signal from one ranked stock. Returns None if it should be skipped."""
    ticker = stock["ticker"]
    last_close = float(df["Close"].iloc[-1])
    breakout_level = stock.get("level_value")
    if breakout_level is None or breakout_level <= 0:
        return None

    atr = _wilder_atr(df)
    if atr is None:
        return None

    notes: list[str] = []

    # Reject already-extended setups: if price has run too far past the level,
    # the trade thesis (buy on the breakout) is gone — chasing here is the
    # exact mistake Qullamaggie warns against.
    overshoot_pct = (last_close - breakout_level) / breakout_level * 100
    if overshoot_pct > MAX_ENTRY_OVERSHOOT_PCT:
        return None

    # Limit entry: a small buffer above the breakout level. Real bot fills
    # only if price actually trades through the level.
    limit_entry = round(breakout_level * (1 + ENTRY_BUFFER_PCT / 100), 2)

    # Stop: entry - 3 × ATR, but never tighter than MIN_STOP_DISTANCE_PCT.
    raw_stop = limit_entry - STOP_ATR_MULTIPLIER * atr
    min_stop = limit_entry * (1 - MIN_STOP_DISTANCE_PCT / 100)
    stop_price = min(raw_stop, min_stop)
    if stop_price < raw_stop:
        notes.append(f"stop floored at {MIN_STOP_DISTANCE_PCT:.0f}% (ATR too tight)")

    stop_distance = limit_entry - stop_price
    if stop_distance <= 0:
        return None
    stop_distance_pct = stop_distance / limit_entry * 100

    # Sizing: risk 1% of account / per-share risk; cap at 20% of account.
    risk_dollars = account_equity * RISK_PER_TRADE_PCT
    raw_shares = risk_dollars / stop_distance
    max_dollar_position = account_equity * MAX_POSITION_PCT
    max_shares_by_cap = max_dollar_position / limit_entry
    shares = int(math.floor(min(raw_shares, max_shares_by_cap)))

    if shares <= 0:
        return None
    if raw_shares > max_shares_by_cap:
        notes.append(
            f"position capped at {MAX_POSITION_PCT * 100:.0f}% of account"
        )

    position_dollars = round(shares * limit_entry, 2)
    position_pct = position_dollars / account_equity * 100

    if last_close < breakout_level:
        gap_pct = (breakout_level - last_close) / last_close * 100
        notes.append(f"needs +{gap_pct:.2f}% to trigger breakout")

    return Signal(
        ticker=ticker,
        name=stock.get("name", ""),
        rank=rank,
        last_close=round(last_close, 2),
        breakout_level=round(float(breakout_level), 2),
        limit_entry=limit_entry,
        stop_price=round(stop_price, 2),
        atr_value=round(atr, 3),
        stop_distance_pct=round(stop_distance_pct, 2),
        risk_dollars=round(risk_dollars, 2),
        shares=shares,
        position_dollars=position_dollars,
        position_pct_of_account=round(position_pct, 2),
        regime=regime,
        level_type=stock.get("level_type", "unknown"),
        sector=stock.get("sector", ""),
        max_hold_days=MAX_HOLD_DAYS,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        notes=notes,
    )


# ── Public entry point ───────────────────────────────────────────────────


def generate_signals(
    watchlist: list[dict],
    regime: str,
    price_data: dict[str, pd.DataFrame],
    account_equity: float = DEFAULT_ACCOUNT_EQUITY,
    max_signals: int = MAX_CONCURRENT_POSITIONS,
) -> tuple[list[Signal], dict]:
    """Generate trade signals from ranked watchlist.

    Returns (signals, summary). Summary explains why no signals were issued
    in the regime gate or other filtering reasons (useful for audit).
    """
    summary: dict = {
        "regime": regime,
        "account_equity": account_equity,
        "tradable_regimes": list(SIGNAL_TRADABLE_REGIMES),
        "candidates_considered": 0,
        "candidates_skipped": 0,
        "skip_reasons": {
            "no_level": 0, "no_atr": 0, "extended": 0,
            "level_too_far": 0, "size_zero": 0,
        },
        "signals_issued": 0,
        "regime_gate_passed": regime in SIGNAL_TRADABLE_REGIMES,
    }

    if regime not in SIGNAL_TRADABLE_REGIMES:
        summary["reason_no_signals"] = (
            f"regime '{regime}' is not in tradable regimes "
            f"({', '.join(SIGNAL_TRADABLE_REGIMES)}); skipping all signals"
        )
        return [], summary

    signals: list[Signal] = []
    # Walk the ranked watchlist top-down until we have max_signals or run out.
    for stock in watchlist:
        if len(signals) >= max_signals:
            break
        summary["candidates_considered"] += 1
        df = price_data.get(stock["ticker"])
        if df is None or len(df) < ATR_PERIOD + 1:
            summary["candidates_skipped"] += 1
            summary["skip_reasons"]["no_atr"] += 1
            continue

        # Quick reject: missing breakout level
        if not stock.get("level_value"):
            summary["candidates_skipped"] += 1
            summary["skip_reasons"]["no_level"] += 1
            continue

        # Quick reject: already extended (saves work in _build_signal)
        last_close = float(df["Close"].iloc[-1])
        bl = float(stock["level_value"])
        gap_pct = (bl - last_close) / last_close * 100
        if -gap_pct > MAX_ENTRY_OVERSHOOT_PCT:
            summary["candidates_skipped"] += 1
            summary["skip_reasons"]["extended"] += 1
            continue
        # Quick reject: breakout level too far above current price to plausibly trigger
        if gap_pct > MAX_LEVEL_DISTANCE_PCT:
            summary["candidates_skipped"] += 1
            summary["skip_reasons"]["level_too_far"] += 1
            continue

        sig = _build_signal(
            stock, df, regime, account_equity, rank=stock.get("rank", len(signals) + 1)
        )
        if sig is None:
            summary["candidates_skipped"] += 1
            summary["skip_reasons"]["size_zero"] += 1
            continue
        signals.append(sig)

    summary["signals_issued"] = len(signals)
    summary["total_capital_committed"] = round(
        sum(s.position_dollars for s in signals), 2
    )
    summary["total_risk"] = round(sum(s.risk_dollars for s in signals), 2)
    return signals, summary


# ── Output helpers ───────────────────────────────────────────────────────


def save_signals(
    signals: list[Signal],
    summary: dict,
    scan_date: dt_date | None = None,
) -> Path:
    """Save signals as JSON to scans/signals_YYYY-MM-DD.json."""
    SCANS_DIR.mkdir(parents=True, exist_ok=True)
    when = scan_date or dt_date.today()
    out_path = SCANS_DIR / f"signals_{when.isoformat()}.json"
    payload = {
        "summary": summary,
        "signals": [asdict(s) for s in signals],
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    return out_path


def print_signals(signals: list[Signal], summary: dict) -> None:
    """Print formatted signals table to terminal."""
    print()
    print("  " + "=" * 92)
    print("  TRADE SIGNALS")
    print("  " + "=" * 92)
    print(
        f"  Account equity: ${summary['account_equity']:,.0f}   "
        f"Regime: {summary['regime']}   "
        f"Risk per trade: {RISK_PER_TRADE_PCT * 100:.1f}%   "
        f"Stop: {STOP_ATR_MULTIPLIER:g}× ATR   "
        f"Max hold: {MAX_HOLD_DAYS}d"
    )

    if not signals:
        reason = summary.get(
            "reason_no_signals",
            f"considered {summary['candidates_considered']}, "
            f"skipped all ({', '.join(f'{k}: {v}' for k, v in summary['skip_reasons'].items() if v)})",
        )
        print(f"  No signals issued — {reason}")
        print()
        return

    print()
    print(
        f"  {'#':>2} {'Ticker':>7} {'Last':>8} {'Entry':>8} "
        f"{'Stop':>8} {'Stop %':>7} {'Shares':>7} {'$ Pos':>10} {'% Acct':>7} {'Level':>13}"
    )
    print("  " + "-" * 90)
    for i, s in enumerate(signals, 1):
        print(
            f"  {i:>2} {s.ticker:>7} {s.last_close:>8.2f} {s.limit_entry:>8.2f} "
            f"{s.stop_price:>8.2f} {s.stop_distance_pct:>6.2f}% "
            f"{s.shares:>7,} ${s.position_dollars:>8,.0f} "
            f"{s.position_pct_of_account:>6.2f}% {s.level_type:>13}"
        )
        for note in s.notes:
            print(f"     ↳ {note}")

    print()
    print(
        f"  Issued {summary['signals_issued']}/{MAX_CONCURRENT_POSITIONS} positions  "
        f"capital ${summary['total_capital_committed']:,.0f}  "
        f"total risk ${summary['total_risk']:,.0f} "
        f"({summary['total_risk'] / summary['account_equity'] * 100:.2f}% of account)"
    )
    print()
