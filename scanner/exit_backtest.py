"""Exit strategy backtest (Phase 10, step 53b).

Re-uses the picks saved by --backtest-multi (13,500 picks across 6 windows)
and simulates several stop / trailing-stop / partial-profit strategies on top.

The plain backtest measures buy-and-hold-N-days returns. That's not what a
real bot would do — the bot needs an initial stop, optionally a trailing
stop, optionally partial profits, and a max hold. This script answers:
which exit policy gives the best risk-adjusted P&L on the same picks?

Usage: python -m scanner --exit-backtest
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date as dt_date
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

from .cache import Cache
from .config import CACHE_DIR, PROJECT_ROOT
from .data import download_prices
from .universe import fetch_ticker_list

BACKTEST_DIR = PROJECT_ROOT / "backtest"
TEST_RESULTS_DIR = PROJECT_ROOT / "test_results"
WINSORIZE_LIMIT = 30.0
ATR_PERIOD = 14
BACKTEST_PERIOD = "3y"


@dataclass(frozen=True)
class ExitStrategy:
    """Defines one exit policy. None means "feature off"."""

    name: str
    initial_stop_atr: float | None = None   # e.g. 2.0 = 2× ATR below entry
    initial_stop_pct: float | None = None   # e.g. 5.0 = 5% below entry
    trailing_stop_atr: float | None = None  # chandelier: highest_close_since_entry - N×ATR
    partial_profit_atr: float | None = None # take 50% off at entry + N×ATR
    max_hold_days: int = 10


STRATEGIES: list[ExitStrategy] = [
    ExitStrategy("baseline_hold_5d", max_hold_days=5),
    ExitStrategy("baseline_hold_10d", max_hold_days=10),
    ExitStrategy("pct_5_10d", initial_stop_pct=5.0, max_hold_days=10),
    ExitStrategy("pct_7_10d", initial_stop_pct=7.0, max_hold_days=10),
    ExitStrategy("atr_2_10d", initial_stop_atr=2.0, max_hold_days=10),
    ExitStrategy("atr_3_10d", initial_stop_atr=3.0, max_hold_days=10),
    ExitStrategy("trail_2_10d", trailing_stop_atr=2.0, max_hold_days=10),
    ExitStrategy("trail_3_10d", trailing_stop_atr=3.0, max_hold_days=10),
    ExitStrategy(
        "atr_2_trail_2_10d",
        initial_stop_atr=2.0,
        trailing_stop_atr=2.0,
        max_hold_days=10,
    ),
    ExitStrategy(
        "atr_2_trail_3_10d",
        initial_stop_atr=2.0,
        trailing_stop_atr=3.0,
        max_hold_days=10,
    ),
    ExitStrategy(
        "partial_atr_2_trail_2_10d",
        initial_stop_atr=2.0,
        partial_profit_atr=2.0,
        trailing_stop_atr=2.0,
        max_hold_days=10,
    ),
    ExitStrategy(
        "atr_2_trail_2_15d",
        initial_stop_atr=2.0,
        trailing_stop_atr=2.0,
        max_hold_days=15,
    ),
]


# ── ATR helper ───────────────────────────────────────────────────────────


def _wilder_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    """ATR using Wilder's smoothing. Returns series aligned with df."""
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
    # Wilder's smoothing == EMA with alpha = 1/period
    return tr.ewm(alpha=1 / period, adjust=False).mean()


# ── Single-trade simulation ──────────────────────────────────────────────


def simulate_trade(
    df: pd.DataFrame,
    entry_idx: int,
    atr: float,
    strategy: ExitStrategy,
) -> dict | None:
    """Simulate one trade according to *strategy*. Returns:
        {pnl_pct, days_held, reason, max_drawdown_pct}
    or None if there isn't enough forward data to test the strategy.
    """
    if entry_idx + 1 >= len(df):
        return None
    if atr <= 0 or not np.isfinite(atr):
        return None

    entry_price = float(df["Close"].iloc[entry_idx])
    if entry_price <= 0:
        return None

    # Initial stop level (computed once at entry, never raised by trail logic
    # — the trail logic produces its own level which we max with this).
    initial_stop: float | None = None
    if strategy.initial_stop_atr is not None:
        initial_stop = entry_price - strategy.initial_stop_atr * atr
    elif strategy.initial_stop_pct is not None:
        initial_stop = entry_price * (1 - strategy.initial_stop_pct / 100)

    highest_close = entry_price
    partial_taken = False
    partial_pnl_contrib = 0.0  # P&L contribution from the half already sold
    remaining_size = 1.0       # fraction of original position still open

    lowest_close_so_far = entry_price  # for max drawdown tracking

    last_offset = min(strategy.max_hold_days, len(df) - 1 - entry_idx)
    if last_offset < 1:
        return None

    for offset in range(1, last_offset + 1):
        i = entry_idx + offset
        day_high = float(df["High"].iloc[i])
        day_low = float(df["Low"].iloc[i])
        day_close = float(df["Close"].iloc[i])

        lowest_close_so_far = min(lowest_close_so_far, day_close)

        # Update trailing stop level for this bar
        current_stop = initial_stop
        if strategy.trailing_stop_atr is not None:
            highest_close = max(highest_close, day_close)
            trail_level = highest_close - strategy.trailing_stop_atr * atr
            current_stop = (
                max(current_stop, trail_level) if current_stop is not None else trail_level
            )

        # Stop hit? Convention: if the day's low touched the stop, we exit at
        # the stop level. Optimistic vs gap-down opens but standard for backtests.
        if current_stop is not None and day_low <= current_stop:
            exit_price = current_stop
            pnl = (exit_price / entry_price - 1) * 100 * remaining_size
            return {
                "pnl_pct": round(pnl + partial_pnl_contrib, 3),
                "days_held": offset,
                "reason": "stop",
                "max_drawdown_pct": round(
                    (lowest_close_so_far / entry_price - 1) * 100, 3
                ),
            }

        # Partial profit trigger (only fires once)
        if (
            strategy.partial_profit_atr is not None
            and not partial_taken
            and remaining_size == 1.0
        ):
            target = entry_price + strategy.partial_profit_atr * atr
            if day_high >= target:
                partial_pnl_contrib = (target / entry_price - 1) * 100 * 0.5
                remaining_size = 0.5
                partial_taken = True

    # Time exit at last_offset close
    exit_price = float(df["Close"].iloc[entry_idx + last_offset])
    pnl = (exit_price / entry_price - 1) * 100 * remaining_size
    return {
        "pnl_pct": round(pnl + partial_pnl_contrib, 3),
        "days_held": last_offset,
        "reason": "time",
        "max_drawdown_pct": round((lowest_close_so_far / entry_price - 1) * 100, 3),
    }


# ── Pick collection ──────────────────────────────────────────────────────


def _load_all_picks() -> list[dict]:
    """Load picks from all multi_window_*.json files. Each pick dict carries
    {ticker, date, regime, window, rank}."""
    picks: list[dict] = []
    for i in range(1, 7):
        path = BACKTEST_DIR / f"multi_window_{i}.json"
        if not path.exists():
            continue
        with open(path) as f:
            data = json.load(f)
        label = data.get("label", f"window_{i}")
        for day in data.get("daily_results", []):
            regime = day.get("regime", "unknown")
            for p in day.get("picks", []):
                picks.append(
                    {
                        "ticker": p["ticker"],
                        "date": day["date"],
                        "regime": regime,
                        "window": i,
                        "window_label": label,
                        "rank": p.get("rank"),
                    }
                )
    return picks


# ── Aggregation ──────────────────────────────────────────────────────────


@dataclass
class StrategyAccum:
    name: str
    trades: list[dict] = field(default_factory=list)


def _winsorize(xs: list[float], limit: float = WINSORIZE_LIMIT) -> list[float]:
    return [max(-limit, min(limit, x)) for x in xs]


def _summarize(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0}
    pnls = [t["pnl_pct"] for t in trades]
    w_pnls = _winsorize(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    days_held = [t["days_held"] for t in trades]
    drawdowns = [t["max_drawdown_pct"] for t in trades]

    win_rate = len(wins) / len(pnls) * 100
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0
    expectancy = (win_rate / 100) * avg_win + (1 - win_rate / 100) * avg_loss

    reason_counts: dict[str, int] = {}
    for t in trades:
        reason_counts[t["reason"]] = reason_counts.get(t["reason"], 0) + 1
    reason_pct = {
        k: round(v / len(trades) * 100, 1) for k, v in reason_counts.items()
    }

    return {
        "n": len(trades),
        "win_rate": round(win_rate, 1),
        "avg_pnl": round(float(np.mean(pnls)), 3),
        "w_avg_pnl": round(float(np.mean(w_pnls)), 3),
        "median_pnl": round(float(np.median(pnls)), 3),
        "avg_win": round(avg_win, 3),
        "avg_loss": round(avg_loss, 3),
        "expectancy": round(expectancy, 3),
        "best": round(max(pnls), 2),
        "worst": round(min(pnls), 2),
        "avg_days_held": round(float(np.mean(days_held)), 2),
        "avg_max_drawdown": round(float(np.mean(drawdowns)), 3),
        "reason_pct": reason_pct,
    }


def _summarize_by_key(
    trades: list[dict], key_fn
) -> dict[str, dict]:
    by_key: dict[str, list[dict]] = {}
    for t in trades:
        k = key_fn(t)
        by_key.setdefault(k, []).append(t)
    return {k: _summarize(v) for k, v in sorted(by_key.items())}


# ── Public entry point ───────────────────────────────────────────────────


def run_exit_backtest():
    """Simulate every strategy on every saved pick, then summarize."""
    start = time.time()
    print()
    print("  Exit Strategy Backtest (Phase 10, step 53b)")
    print("  " + "=" * 50)
    print()

    # 1. Load saved picks
    print("[1/4] Loading picks from multi_window_*.json...")
    picks = _load_all_picks()
    if not picks:
        print("  ERROR: No multi_window_*.json files found.")
        print("  Run --backtest-multi first.")
        return
    print(f"  Loaded {len(picks):,} picks across 6 windows")

    # 2. Load price data (cached parquet, fast)
    print()
    print("[2/4] Loading 3 years of price data (cached)...")
    cache = Cache(CACHE_DIR)
    raw_tickers = fetch_ticker_list(cache)
    price_data = download_prices(raw_tickers, cache, period=BACKTEST_PERIOD)
    print(f"  Have data for {len(price_data):,} tickers")

    # 3. Pre-compute ATR per ticker once
    print()
    print("[3/4] Computing ATR series per ticker...")
    atr_data: dict[str, pd.Series] = {}
    for ticker, df in price_data.items():
        if len(df) < ATR_PERIOD + 1:
            continue
        atr_data[ticker] = _wilder_atr(df)

    # 4. Simulate every strategy on every pick
    print()
    print("[4/4] Simulating strategies...")
    accums = {s.name: StrategyAccum(s.name) for s in STRATEGIES}
    skipped = 0

    for pick in tqdm(picks, desc="  Trades", unit="pick"):
        ticker = pick["ticker"]
        df = price_data.get(ticker)
        atr_series = atr_data.get(ticker)
        if df is None or atr_series is None:
            skipped += 1
            continue
        try:
            entry_idx = df.index.get_loc(pd.Timestamp(pick["date"]))
        except KeyError:
            skipped += 1
            continue
        if isinstance(entry_idx, slice) or not isinstance(entry_idx, int):
            skipped += 1
            continue
        atr = float(atr_series.iloc[entry_idx])
        if not np.isfinite(atr) or atr <= 0:
            skipped += 1
            continue

        for strategy in STRATEGIES:
            result = simulate_trade(df, entry_idx, atr, strategy)
            if result is None:
                continue
            accums[strategy.name].trades.append(
                {
                    **result,
                    "regime": pick["regime"],
                    "window": pick["window"],
                    "rank": pick["rank"],
                }
            )

    if skipped:
        print(f"  Skipped {skipped:,} picks (missing data or ATR)")

    # 5. Summarize
    print()
    print("[5/4] Summarizing...")
    overall: dict[str, dict] = {}
    by_regime: dict[str, dict] = {}
    by_window: dict[str, dict] = {}
    by_rank_bucket: dict[str, dict] = {}

    def _rank_bucket(t):
        r = t.get("rank") or 99
        return "top5" if r <= 5 else ("rank6_10" if r <= 10 else "rank11_20")

    for s in STRATEGIES:
        trades = accums[s.name].trades
        overall[s.name] = _summarize(trades)
        by_regime[s.name] = _summarize_by_key(trades, lambda t: t["regime"])
        by_window[s.name] = _summarize_by_key(trades, lambda t: f"window_{t['window']}")
        by_rank_bucket[s.name] = _summarize_by_key(trades, _rank_bucket)

    # 6. Save JSON
    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
    out: dict = {
        "ran_at": dt_date.today().isoformat(),
        "n_picks_total": len(picks),
        "n_picks_skipped": skipped,
        "strategies": [
            {
                "name": s.name,
                "initial_stop_atr": s.initial_stop_atr,
                "initial_stop_pct": s.initial_stop_pct,
                "trailing_stop_atr": s.trailing_stop_atr,
                "partial_profit_atr": s.partial_profit_atr,
                "max_hold_days": s.max_hold_days,
            }
            for s in STRATEGIES
        ],
        "overall": overall,
        "by_regime": by_regime,
        "by_window": by_window,
        "by_rank_bucket": by_rank_bucket,
    }
    json_path = BACKTEST_DIR / "exit_strategies.json"
    with open(json_path, "w") as f:
        json.dump(out, f, indent=2)

    # 7. Print + save markdown
    _print_summary(overall, by_regime)
    md_path = _save_markdown(out)

    elapsed = time.time() - start
    print()
    print(f"  Done in {elapsed:.1f}s")
    print(f"  JSON:     {json_path}")
    print(f"  Markdown: {md_path}")
    print()


# ── Pretty printing ──────────────────────────────────────────────────────


def _print_summary(overall: dict, by_regime: dict) -> None:
    print()
    print("  " + "=" * 88)
    print("  OVERALL — Per-trade P&L by exit strategy")
    print("  " + "=" * 88)
    print(
        f"  {'Strategy':>27} {'N':>6} {'Win%':>6} {'Avg':>7} "
        f"{'W.Avg':>7} {'Med':>7} {'Exp':>7} {'AvgDays':>8}"
    )
    # Sort by expectancy descending so the winner pops out
    ranked = sorted(
        overall.items(),
        key=lambda kv: kv[1].get("expectancy", -999),
        reverse=True,
    )
    for name, s in ranked:
        if not s or not s.get("n"):
            continue
        print(
            f"  {name:>27} {s['n']:>6} {s['win_rate']:>5.1f}% "
            f"{s['avg_pnl']:>+6.2f}% {s['w_avg_pnl']:>+6.2f}% "
            f"{s['median_pnl']:>+6.2f}% {s['expectancy']:>+6.2f}% "
            f"{s['avg_days_held']:>7.1f}"
        )

    print()
    print("  " + "=" * 88)
    print("  By Regime — winner strategy in each regime")
    print("  " + "=" * 88)
    regimes = ("favorable", "mixed", "caution")
    for regime in regimes:
        bests: list[tuple[str, dict]] = []
        for name, by_r in by_regime.items():
            stats = by_r.get(regime)
            if stats and stats.get("n", 0) >= 100:
                bests.append((name, stats))
        if not bests:
            continue
        bests.sort(key=lambda kv: kv[1]["expectancy"], reverse=True)
        print()
        print(f"  Regime: {regime}  (top 5 by expectancy)")
        print(
            f"  {'Strategy':>27} {'N':>6} {'Win%':>6} {'W.Avg':>7} "
            f"{'Median':>7} {'Exp':>7}"
        )
        for name, s in bests[:5]:
            print(
                f"  {name:>27} {s['n']:>6} {s['win_rate']:>5.1f}% "
                f"{s['w_avg_pnl']:>+6.2f}% {s['median_pnl']:>+6.2f}% "
                f"{s['expectancy']:>+6.2f}%"
            )


def _save_markdown(out: dict) -> Path:
    today = out["ran_at"]
    lines: list[str] = []
    lines.append(f"# Exit Strategy Backtest — {today}")
    lines.append("")
    lines.append(
        f"Simulated {len(out['strategies'])} exit strategies on "
        f"{out['n_picks_total']:,} picks (skipped {out['n_picks_skipped']:,} for missing data) "
        f"from the 6-window multi_window backtest. Picks come from v5 quality-first ranking. "
        f"Entry = close on pick day, ATR = Wilder({ATR_PERIOD}) at entry. "
        f"Stop fills assumed at the stop price when day's Low touches it (no slippage modeled — "
        f"a real bot will see slippage on gap-downs). Returns winsorized at +/-{int(WINSORIZE_LIMIT)}%."
    )
    lines.append("")

    lines.append("## Overall — ranked by expectancy")
    lines.append("")
    lines.append(
        "| Strategy | N | Win % | Avg | W.Avg | Median | Best | Worst | Expectancy | Avg Days | Avg DD |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|---|---|---|"
    )
    ranked = sorted(
        out["overall"].items(),
        key=lambda kv: kv[1].get("expectancy", -999),
        reverse=True,
    )
    for name, s in ranked:
        if not s.get("n"):
            continue
        lines.append(
            f"| {name} | {s['n']:,} | {s['win_rate']:.1f}% | "
            f"{s['avg_pnl']:+.2f}% | {s['w_avg_pnl']:+.2f}% | "
            f"{s['median_pnl']:+.2f}% | {s['best']:+.2f}% | {s['worst']:+.2f}% | "
            f"{s['expectancy']:+.2f}% | {s['avg_days_held']:.1f} | "
            f"{s['avg_max_drawdown']:+.2f}% |"
        )
    lines.append("")

    lines.append("## Exit reason mix (overall)")
    lines.append("")
    lines.append("| Strategy | stop % | time % | other |")
    lines.append("|---|---|---|---|")
    for name, s in ranked:
        if not s.get("n"):
            continue
        rp = s.get("reason_pct", {})
        lines.append(
            f"| {name} | {rp.get('stop', 0):.1f}% | "
            f"{rp.get('time', 0):.1f}% | "
            f"{', '.join(f'{k}={v}%' for k, v in rp.items() if k not in ('stop', 'time')) or '-'} |"
        )
    lines.append("")

    # By regime
    lines.append("## By regime — top 5 strategies per regime (by expectancy)")
    lines.append("")
    for regime in ("favorable", "mixed", "caution"):
        bests: list[tuple[str, dict]] = []
        for name, by_r in out["by_regime"].items():
            stats = by_r.get(regime)
            if stats and stats.get("n", 0) >= 100:
                bests.append((name, stats))
        if not bests:
            continue
        bests.sort(key=lambda kv: kv[1]["expectancy"], reverse=True)
        lines.append(f"### {regime}")
        lines.append("")
        lines.append("| Strategy | N | Win % | W.Avg | Median | Expectancy |")
        lines.append("|---|---|---|---|---|---|")
        for name, s in bests[:5]:
            lines.append(
                f"| {name} | {s['n']:,} | {s['win_rate']:.1f}% | "
                f"{s['w_avg_pnl']:+.2f}% | {s['median_pnl']:+.2f}% | "
                f"{s['expectancy']:+.2f}% |"
            )
        lines.append("")

    # Per-window for the top 3 overall strategies
    lines.append("## Per-window expectancy — top 3 strategies overall")
    lines.append("")
    top3 = [name for name, _ in ranked[:3]]
    if top3:
        lines.append("| Strategy | " + " | ".join(f"W{i}" for i in range(1, 7)) + " |")
        lines.append("|---" * 7 + "|")
        for name in top3:
            row = [name]
            for i in range(1, 7):
                stats = out["by_window"][name].get(f"window_{i}")
                if stats and stats.get("n"):
                    row.append(f"{stats['expectancy']:+.2f}%")
                else:
                    row.append("—")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    md_path = TEST_RESULTS_DIR / f"{today}_exit_strategies.md"
    TEST_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines))
    return md_path
