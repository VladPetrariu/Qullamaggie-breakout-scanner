"""Full paper-trading account report (--paper-report).

Read-only: renders everything the simulator has persisted — account
overview, closed-trade statistics, the signal funnel, progress against
the Phase 10 go-live gate, and the full day-by-day equity history.
Run `--paper` first to bring the account up to date.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from math import ceil, sqrt
from pathlib import Path

from .cache import Cache
from .config import CACHE_DIR, MAX_OPEN_POSITIONS, PAPER_DIR
from .paper_simulator import (
    _account_path,
    _load_account,
    _load_trades,
    _max_drawdown_pct,
)

# Go-live gate: expectancy measured in R, with evidence from the live-exit
# backtest audit. See test_results/2026-09-16_live_trade_audit.md.
GATE_MIN_TRADES = 60
GATE_BACKTEST_EXPECTANCY_R = 0.081  # partial3_trail3, top-5 favorable+mixed
GATE_WIN_RATE_RANGE = (47.0, 56.0)  # multi-window 5d backtest range
GATE_MAX_DRAWDOWN_PCT = 10.0
GATE_MIN_TRADES_FOR_WIN_RATE = 30
GATE_Z_95 = 1.96

SPARK_BLOCKS = "▁▂▃▄▅▆▇█"


# ── Pure computations (unit-tested) ──────────────────────────────────────


def _trade_stats(trades: list[dict]) -> dict:
    """Aggregate statistics over closed trades."""
    stats: dict = {"n": len(trades)}
    if not trades:
        return stats

    wins = [t for t in trades if t["pnl_dollars"] > 0]
    losses = [t for t in trades if t["pnl_dollars"] <= 0]
    gross_profit = sum(t["pnl_dollars"] for t in wins)
    gross_loss = sum(t["pnl_dollars"] for t in losses)  # <= 0

    best = max(trades, key=lambda t: t["pnl_pct"])
    worst = min(trades, key=lambda t: t["pnl_pct"])

    r_values = [
        t["pnl_dollars"] / t["risk_dollars"]
        for t in trades
        if isinstance(t.get("risk_dollars"), (int, float)) and t["risk_dollars"] > 0
    ]
    r_n = len(r_values)
    r_mean = sum(r_values) / r_n if r_n else None
    r_std = sqrt(sum((value - r_mean) ** 2 for value in r_values) / (r_n - 1)) if r_n > 1 else None
    r_ci = _mean_ci_95(r_values) if r_n >= 2 and r_n == len(trades) else None

    stats.update({
        "r_n": r_n,
        "mean_r": r_mean,
        "std_r": r_std,
        "mean_r_ci": r_ci,
        "trades_missing_risk": len(trades) - r_n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(trades) * 100,
        "realized_pnl": gross_profit + gross_loss,
        "avg_win": gross_profit / len(wins) if wins else 0.0,
        "avg_loss": gross_loss / len(losses) if losses else 0.0,
        "profit_factor": (gross_profit / -gross_loss) if gross_loss < 0 else None,
        "expectancy": (gross_profit + gross_loss) / len(trades),
        "avg_days_held": sum(t["days_held"] for t in trades) / len(trades),
        "best": (best["ticker"], best["pnl_pct"]),
        "worst": (worst["ticker"], worst["pnl_pct"]),
        "exit_reasons": dict(Counter(t["exit_reason"] for t in trades)),
        "avg_mae": sum(t["mae_pct"] for t in trades) / len(trades),
        "avg_mfe": sum(t["mfe_pct"] for t in trades) / len(trades),
    })
    return stats


def _funnel(order_history: list[dict], pending: list[dict]) -> dict:
    counts = Counter(o["status"] for o in order_history)
    named = ("filled", "not_triggered", "gapped_past_entry", "superseded", "stale", "no_data")
    funnel = {
        "loaded": len(order_history) + len(pending),
        "skipped": sum(v for k, v in counts.items() if k.startswith("skipped")),
        "other": sum(
            v for k, v in counts.items()
            if k not in named and not k.startswith("skipped")
        ),
        "pending": len(pending),
    }
    for key in named:
        funnel[key] = counts.get(key, 0)
    # Orders that reached a fill decision on their trade day — superseded,
    # stale, and no-data orders never had the chance, so they don't belong
    # in the fill-rate denominator.
    funnel["attempted"] = (
        funnel["filled"] + funnel["not_triggered"] + funnel["gapped_past_entry"]
    )
    return funnel


def _wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% CI for a win rate, in percent."""
    if n == 0:
        return 0.0, 100.0
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return center * 100 - half * 100, center * 100 + half * 100


def _t_critical_95(df: int) -> float:
    """Two-sided 95% Student-t critical value; normal approximation after 30 df."""
    critical = {
        1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
        6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
        16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
        21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
        26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
    }
    return critical.get(df, 1.96)


def _mean_ci_95(values: list[float]) -> tuple[float, float] | None:
    """Student-t 95% confidence interval for a sample mean."""
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    std = sqrt(sum((value - mean) ** 2 for value in values) / (n - 1))
    margin = _t_critical_95(n - 1) * std / sqrt(n)
    return mean - margin, mean + margin


def _trades_needed_2sigma(std_r: float | None, mean_r: float | None) -> int | None:
    """Approximate sample size needed to distinguish the observed mean from zero."""
    if std_r is None or mean_r is None or abs(mean_r) < 1e-12:
        return None
    return max(1, ceil((GATE_Z_95 * std_r / abs(mean_r)) ** 2))


def _spy_return_pct(curve: list[dict]) -> float | None:
    """Read SPY's matching-period return from the local cache; never downloads."""
    if not curve:
        return None
    try:
        prices = Cache(CACHE_DIR).get_df(
            f"prices_{date.today().isoformat()}", max_age_hours=float("inf")
        )
        if prices is None or "Ticker" not in prices.columns or "Close" not in prices.columns:
            return None
        spy = prices.loc[prices["Ticker"] == "SPY", "Close"].dropna().sort_index()
        if spy.empty:
            return None
        start_day, end_day = date.fromisoformat(curve[0]["date"]), date.fromisoformat(curve[-1]["date"])
        matched = spy.loc[(spy.index.date >= start_day) & (spy.index.date <= end_day)]
        if len(matched) < 2 or float(matched.iloc[0]) <= 0:
            return None
        return (float(matched.iloc[-1]) / float(matched.iloc[0]) - 1) * 100
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _gate_status(
    stats: dict,
    total_return_pct: float,
    max_dd_pct: float,
    spy_return_pct: float | None = None,
) -> list[tuple]:
    """Progress against the go-live gate; met is True, False, or None."""
    n, r_n = stats.get("n", 0), stats.get("r_n", 0)
    mean_r, std_r, ci = stats.get("mean_r"), stats.get("std_r"), stats.get("mean_r_ci")
    needed = _trades_needed_2sigma(std_r, mean_r)
    rows = [(
        f"{GATE_MIN_TRADES}+ closed trades",
        True if n >= GATE_MIN_TRADES else False,
        f"{n}/{GATE_MIN_TRADES}",
    )]

    if ci is not None:
        ci_lo, ci_hi = ci
        edge_met = ci_lo > 0
        se_r = std_r / sqrt(r_n) if std_r is not None and r_n else 0.0
        edge_detail = f"mean {mean_r:+.3f}R (SE {se_r:.3f}R) [95% CI {ci_lo:+.3f} to {ci_hi:+.3f}R; n={r_n}]"
    else:
        edge_met = None
        missing = stats.get("trades_missing_risk", 0)
        edge_detail = (
            f"R unavailable for {missing} trade(s); need valid risk_dollars and 2+ trades"
            if missing or r_n < 2 else "insufficient R data"
        )
    rows.append(("lower 95% bound of mean R > 0", edge_met, edge_detail))

    consistency_met = None
    if ci is not None and n >= GATE_MIN_TRADES:
        ci_lo, ci_hi = ci
        consistency_met = ci_lo <= GATE_BACKTEST_EXPECTANCY_R <= ci_hi
        consistency_detail = (
            f"backtest {GATE_BACKTEST_EXPECTANCY_R:+.3f}R; live CI "
            f"{ci_lo:+.3f} to {ci_hi:+.3f}R (n={r_n})"
        )
    else:
        consistency_detail = (
            f"backtest {GATE_BACKTEST_EXPECTANCY_R:+.3f}R; "
            f"need {GATE_MIN_TRADES}+ trades with valid risk data"
        )
    rows.append(("live mean R consistent with backtest", consistency_met, consistency_detail))

    sample_met = None if needed is None else r_n >= needed
    sample_detail = (
        f"need more data to estimate (n={r_n})" if needed is None
        else f"~{needed} trades at observed mean/std (n={r_n})"
    )
    rows.append(("sample size to resolve observed edge at 2σ", sample_met, sample_detail))
    rows.append((
        "SPY return over matching period",
        None if spy_return_pct is None else True,
        "unavailable in local price cache" if spy_return_pct is None else f"{spy_return_pct:+.2f}%",
    ))

    lo, hi = GATE_WIN_RATE_RANGE
    if n >= GATE_MIN_TRADES_FOR_WIN_RATE:
        wr = stats["win_rate"]
        ci_lo, ci_hi = _wilson_ci(stats["wins"], n)
        rows.append((
            f"win rate consistent with backtest ({lo:.0f}-{hi:.0f}%)",
            ci_hi >= lo,
            f"{wr:.1f}% [CI {ci_lo:.1f}-{ci_hi:.1f}] (n={n})",
        ))
    else:
        wr_txt = f"{stats['win_rate']:.1f}% " if n else ""
        rows.append((
            f"win rate consistent with backtest ({lo:.0f}-{hi:.0f}%)",
            None,
            f"{wr_txt}(n={n} — need {GATE_MIN_TRADES_FOR_WIN_RATE}+ to judge)",
        ))

    rows.append((
        f"max drawdown < {GATE_MAX_DRAWDOWN_PCT:.0f}%",
        abs(max_dd_pct) < GATE_MAX_DRAWDOWN_PCT,
        f"{max_dd_pct:.2f}%",
    ))
    return rows

def _sparkline(values: list[float]) -> str:
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    if hi == lo:
        return SPARK_BLOCKS[0] * len(values)
    return "".join(
        SPARK_BLOCKS[int((v - lo) / (hi - lo) * (len(SPARK_BLOCKS) - 1))]
        for v in values
    )


def _daily_rows(curve: list[dict], starting_equity: float) -> list[dict]:
    rows = []
    prev = starting_equity
    for point in curve:
        eq = point["equity"]
        rows.append({
            "date": point["date"],
            "equity": eq,
            "day_pnl": eq - prev,
            "day_pct": (eq / prev - 1) * 100 if prev > 0 else 0.0,
            "cum_pct": (eq / starting_equity - 1) * 100 if starting_equity > 0 else 0.0,
            "open": point.get("open_positions", 0),
        })
        prev = eq
    return rows


# ── Rendering ────────────────────────────────────────────────────────────


def print_full_report(*, paper_dir: Path = PAPER_DIR) -> None:
    if not _account_path(paper_dir).exists():
        print()
        print("  No paper account yet — run `python -m scanner --paper` first.")
        print()
        return

    state = _load_account(paper_dir, None)
    trades = _load_trades(paper_dir)
    curve = state["equity_curve"]
    start_eq = state["starting_equity"]

    equity = curve[-1]["equity"] if curve else start_eq
    total_ret = (equity / start_eq - 1) * 100
    max_dd = _max_drawdown_pct(curve, start_eq)
    peak = max([start_eq] + [p["equity"] for p in curve])
    current_dd = (equity / peak - 1) * 100 if peak > 0 else 0.0
    unrealized = sum(
        (p["last_mark_close"] - p["fill_price"]) * p["shares"]
        for p in state["open_positions"]
    )
    # Partials already banked on still-open positions are realized cash but
    # appear in no closed trade yet — without them Realized + Unrealized
    # stops reconciling with equity as soon as the first partial fills.
    banked_partials = sum(
        p.get("partial_pnl_dollars", 0.0) for p in state["open_positions"]
    )
    market_value = sum(
        p["last_mark_close"] * p["shares"] for p in state["open_positions"]
    )
    stats = _trade_stats(trades)

    print()
    print("  " + "=" * 92)
    print("  PAPER TRADING REPORT")
    print("  " + "=" * 92)
    inception = curve[0]["date"] if curve else "—"
    as_of = state["last_processed_date"] or "—"
    print(
        f"  Inception {inception}   As of {as_of}   "
        f"Trading days {len(curve)}"
    )
    print(
        f"  Equity ${equity:,.2f}  ({total_ret:+.2f}% total)   "
        f"Cash ${state['cash']:,.2f}   Positions ${market_value:,.2f} "
        f"({len(state['open_positions'])}/{MAX_OPEN_POSITIONS})"
    )
    realized = stats.get("realized_pnl", 0.0) + banked_partials
    banked_note = (
        f" (incl. ${banked_partials:+,.2f} banked partials on open positions)"
        if banked_partials else ""
    )
    print(
        f"  Realized P&L ${realized:+,.2f}{banked_note}   "
        f"Unrealized ${unrealized:+,.2f}   "
        f"Max DD {max_dd:.2f}%   Current DD {current_dd:.2f}%"
    )

    if trades:
        print()
        print("  TRADE STATISTICS")
        pf = stats["profit_factor"]
        print(
            f"  Closed {stats['n']} ({stats['wins']}W/{stats['losses']}L, "
            f"{stats['win_rate']:.1f}% win rate)   "
            f"Expectancy ${stats['expectancy']:+,.2f}/trade   "
            f"Profit factor {'∞' if pf is None else f'{pf:.2f}'}"
        )
        print(
            f"  Avg win ${stats['avg_win']:+,.2f}   Avg loss ${stats['avg_loss']:+,.2f}   "
            f"Avg hold {stats['avg_days_held']:.1f}d   "
            f"Best {stats['best'][0]} {stats['best'][1]:+.1f}%   "
            f"Worst {stats['worst'][0]} {stats['worst'][1]:+.1f}%"
        )
        reasons = ", ".join(f"{k} {v}" for k, v in sorted(stats["exit_reasons"].items()))
        print(
            f"  Exits: {reasons}   "
            f"Avg MAE {stats['avg_mae']:+.1f}%   Avg MFE {stats['avg_mfe']:+.1f}%"
        )

    funnel = _funnel(state["order_history"], state["pending_orders"])
    if funnel["loaded"]:
        print()
        print("  SIGNAL FUNNEL")
        fill_rate = (
            funnel["filled"] / funnel["attempted"] * 100 if funnel["attempted"] else 0.0
        )
        print(
            f"  Signals {funnel['loaded']}   Filled {funnel['filled']} "
            f"({fill_rate:.0f}% of attempted)   Not triggered {funnel['not_triggered']}   "
            f"Gapped past entry {funnel['gapped_past_entry']}   "
            f"Skipped {funnel['skipped']}   Superseded {funnel['superseded']}   "
            f"Pending {funnel['pending']}"
        )
        extras = {"Stale": funnel["stale"], "No data": funnel["no_data"], "Other": funnel["other"]}
        line = "   ".join(f"{k} {v}" for k, v in extras.items() if v)
        if line:
            print(f"  {line}")

    print()
    print("  GO-LIVE GATE  (Phase 10 criteria)")
    spy_return = _spy_return_pct(curve)
    for label, met, detail in _gate_status(stats, total_ret, max_dd, spy_return):
        mark = "✓" if met else ("·" if met is None else "✗")
        print(f"  [{mark}] {label:<46} {detail}")

    if curve:
        print()
        print("  DAILY EQUITY")
        spark = _sparkline([p["equity"] for p in curve])
        if spark:
            print(f"  {spark}")
        print(
            f"  {'Date':>12} {'Equity':>12} {'Day P&L':>10} {'Day %':>8} "
            f"{'Cum %':>8} {'Open':>5}"
        )
        for row in _daily_rows(curve, start_eq):
            print(
                f"  {row['date']:>12} {row['equity']:>12,.2f} "
                f"{row['day_pnl']:>+10.2f} {row['day_pct']:>+7.2f}% "
                f"{row['cum_pct']:>+7.2f}% {row['open']:>5}"
            )
    print()
