"""Walk-forward backtesting engine.

For each trading day in the test window, computes what the scanner would have
output using only data available up to that day (no lookahead), then measures
forward returns at 1/3/5/10 day horizons.

Usage: python -m scanner --backtest
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

from .cache import Cache
from .config import (
    CACHE_DIR,
    MIN_AVG_VOLUME,
    MIN_PRICE,
    PROJECT_ROOT,
    VOLUME_AVG_PERIOD,
)
from .data import download_prices
from .factors.breakout_level import compute_breakout_level
from .factors.catalyst import compute_catalyst
from .factors.consolidation import compute_consolidation
from .factors.market_context import compute_market_context
from .factors.relative_strength import compute_universe_rs
from .factors.volume import compute_volume
from .factors.weekly import compute_weekly
from .profile import compute_abr
from .ranking import rank_watchlist
from .universe import fetch_ticker_list

BACKTEST_DIR = PROJECT_ROOT / "backtest"
BACKTEST_PERIOD = "2y"
TEST_WINDOW_DAYS = 120  # last ~6 months of trading days
TOP_N = 20
FORWARD_HORIZONS = [1, 3, 5, 10]

# Factors saved per pick (for quintile analysis)
_SAVED_FACTORS = [
    "rs_percentile",
    "rs_direction",
    "atr_compression",
    "freshness_score",
    "ema_stack",
    "level_type",
    "weekly_confluence",
    "vol_ratio_50d",
    "hh_hl_pct",
    "candle_label",
    "has_pole",
    "flag_vol_label",
]


# ── Public entry point ────────────────────────────────────────────────────


def run_backtest():
    """Run walk-forward backtest and print results."""
    start = time.time()
    print()
    print("  Qullamaggie Breakout Scanner — Backtest")
    print("  " + "=" * 45)
    print()

    cache = Cache(CACHE_DIR)
    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Download 2 years of data ───────────────────────────────
    print("[1/4] Downloading 2 years of price data...")
    raw_tickers = fetch_ticker_list(cache)
    price_data = download_prices(raw_tickers, cache, period=BACKTEST_PERIOD)
    print(f"  Received data for {len(price_data):,} tickers")

    # ── 2. Determine test window ──────────────────────────────────
    spy = price_data.get("SPY")
    if spy is None or len(spy) < TEST_WINDOW_DAYS + 50:
        print("  ERROR: Not enough SPY data for backtest")
        return

    all_dates = spy.index
    max_fwd = max(FORWARD_HORIZONS)
    # Reserve max_fwd days at the end for forward return measurement
    test_dates = all_dates[-(TEST_WINDOW_DAYS + max_fwd) : -max_fwd]

    print(
        f"  Testing {len(test_dates)} trading days: "
        f"{test_dates[0].date()} to {test_dates[-1].date()}"
    )

    # ── 3. Walk-forward simulation ────────────────────────────────
    print()
    print("[2/4] Walk-forward simulation...")

    daily_results: list[dict] = []
    checkpoint_path = BACKTEST_DIR / "checkpoint.json"

    # Resume from checkpoint if available
    completed_dates: set[str] = set()
    if checkpoint_path.exists():
        try:
            with open(checkpoint_path) as f:
                saved = json.load(f)
            daily_results = saved.get("daily_results", [])
            completed_dates = {r["date"] for r in daily_results}
            print(f"  Resuming from checkpoint ({len(completed_dates)} days done)")
        except (json.JSONDecodeError, KeyError):
            pass

    for i, date in enumerate(tqdm(test_dates, desc="  Backtesting", unit="day")):
        date_str = date.strftime("%Y-%m-%d")
        if date_str in completed_dates:
            continue

        # Slice all price data up to this date (no lookahead)
        sliced = _slice_data(price_data, date)

        # Filter universe using sliced data
        universe = _filter_universe_at(raw_tickers, sliced)
        if len(universe) < 50:
            daily_results.append(
                {"date": date_str, "regime": "insufficient_data", "picks": []}
            )
            continue

        # Market context
        ctx = compute_market_context(sliced, universe)
        regime = ctx["regime"]

        if regime == "risk_off":
            daily_results.append(
                {"date": date_str, "regime": "risk_off", "picks": []}
            )
            continue

        # Relative strength (universe-wide)
        rs_data = compute_universe_rs(sliced, universe)

        # Per-stock factors
        watchlist: list[dict] = []
        for ticker in universe:
            df = sliced.get(ticker)
            if df is None:
                continue

            consol = compute_consolidation(ticker, df)
            if consol is None:
                continue

            rs = rs_data.get(ticker)
            if rs is None:
                continue

            abr = compute_abr(df)
            cat = compute_catalyst(ticker, df) or {}
            vol = compute_volume(ticker, df) or {}
            bl = compute_breakout_level(ticker, df) or {}
            wk = compute_weekly(ticker, df) or {}

            watchlist.append(
                {"ticker": ticker, "abr": abr, **rs, **consol, **cat, **vol, **bl, **wk}
            )

        # Rank and take top N
        watchlist = rank_watchlist(watchlist)
        top = watchlist[:TOP_N]

        # Record picks with forward returns
        picks = []
        for rank, stock in enumerate(top, 1):
            fwd = _forward_returns(price_data, stock["ticker"], date)
            picks.append(
                {
                    "ticker": stock["ticker"],
                    "rank": rank,
                    "factors": {k: stock.get(k) for k in _SAVED_FACTORS},
                    "forward_returns": fwd,
                }
            )

        daily_results.append(
            {
                "date": date_str,
                "regime": regime,
                "universe_size": len(universe),
                "watchlist_size": len(watchlist),
                "picks": picks,
            }
        )

        # Checkpoint every 10 days
        if (i + 1) % 10 == 0:
            _save_checkpoint(checkpoint_path, daily_results)

    # ── 4. Analyse results ────────────────────────────────────────
    print()
    print("[3/4] Analyzing results...")
    analysis = _analyze_results(daily_results)

    # ── 5. Save ───────────────────────────────────────────────────
    print()
    print("[4/4] Saving results...")
    results = {
        "test_period": {
            "start": test_dates[0].strftime("%Y-%m-%d"),
            "end": test_dates[-1].strftime("%Y-%m-%d"),
            "trading_days": len(test_dates),
        },
        "daily_results": daily_results,
        "analysis": analysis,
    }

    results_path = BACKTEST_DIR / "results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    checkpoint_path.unlink(missing_ok=True)

    _print_summary(analysis)

    elapsed = time.time() - start
    print()
    print(f"  Done in {elapsed:.1f}s")
    print(f"  Results saved to {results_path}")
    print()


# ── Data helpers ──────────────────────────────────────────────────────────


def _slice_data(
    price_data: dict[str, pd.DataFrame], end_date: pd.Timestamp
) -> dict[str, pd.DataFrame]:
    """Slice all DataFrames to end on *end_date* (inclusive). No lookahead."""
    sliced: dict[str, pd.DataFrame] = {}
    for ticker, df in price_data.items():
        s = df.loc[:end_date]
        if len(s) > 0:
            sliced[ticker] = s
    return sliced


def _filter_universe_at(
    tickers: list[str], sliced: dict[str, pd.DataFrame]
) -> list[str]:
    """Filter universe using sliced (point-in-time) data."""
    passed = []
    for ticker in tickers:
        df = sliced.get(ticker)
        if df is None or len(df) < VOLUME_AVG_PERIOD:
            continue
        recent = df.tail(VOLUME_AVG_PERIOD)
        avg_vol = recent["Volume"].mean()
        last_close = float(df["Close"].iloc[-1])
        if last_close >= MIN_PRICE and avg_vol >= MIN_AVG_VOLUME:
            passed.append(ticker)
    return sorted(passed)


def _forward_returns(
    price_data: dict[str, pd.DataFrame],
    ticker: str,
    from_date: pd.Timestamp,
) -> dict[int, float | None]:
    """Compute forward returns at each horizon from *from_date*.

    Uses the FULL (unsliced) price_data so we can see into the future
    for measurement purposes only.
    """
    df = price_data.get(ticker)
    if df is None:
        return {h: None for h in FORWARD_HORIZONS}

    try:
        idx = df.index.get_loc(from_date)
    except KeyError:
        return {h: None for h in FORWARD_HORIZONS}

    close_at = float(df["Close"].iloc[idx])
    result: dict[int, float | None] = {}
    for h in FORWARD_HORIZONS:
        if idx + h < len(df):
            future = float(df["Close"].iloc[idx + h])
            result[h] = round((future / close_at - 1) * 100, 2)
        else:
            result[h] = None
    return result


def _save_checkpoint(path: Path, daily_results: list[dict]) -> None:
    with open(path, "w") as f:
        json.dump({"daily_results": daily_results}, f, default=str)


# ── Analysis ──────────────────────────────────────────────────────────────


def _all_picks(daily_results: list[dict]) -> list[dict]:
    """Flatten all picks across all days."""
    picks = []
    for day in daily_results:
        for pick in day.get("picks", []):
            picks.append(pick)
    return picks


def _get_return(pick: dict, horizon: int) -> float | None:
    """Extract forward return, handling both int and str keys (JSON round-trip)."""
    fwd = pick.get("forward_returns", {})
    val = fwd.get(horizon)
    if val is None:
        val = fwd.get(str(horizon))
    return val


def _returns_for_horizon(picks: list[dict], horizon: int) -> list[float]:
    """Collect non-None returns at a given horizon."""
    return [r for p in picks if (r := _get_return(p, horizon)) is not None]


def _analyze_results(daily_results: list[dict]) -> dict:
    """Compute summary statistics from backtest daily results."""
    picks = _all_picks(daily_results)
    if not picks:
        return {"error": "No picks to analyze"}

    analysis: dict = {}

    # ── Overall per-horizon stats ─────────────────────────────────
    per_horizon = {}
    for h in FORWARD_HORIZONS:
        rets = _returns_for_horizon(picks, h)
        if rets:
            per_horizon[h] = {
                "n": len(rets),
                "win_rate": round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1),
                "avg_return": round(float(np.mean(rets)), 2),
                "median_return": round(float(np.median(rets)), 2),
                "best": round(max(rets), 2),
                "worst": round(min(rets), 2),
            }
    analysis["per_horizon"] = per_horizon

    # ── Top-5 vs Top-20 ──────────────────────────────────────────
    top5 = [p for p in picks if p["rank"] <= 5]
    rank_analysis = {}
    for h in FORWARD_HORIZONS:
        t5 = _returns_for_horizon(top5, h)
        t20 = _returns_for_horizon(picks, h)
        if t5 and t20:
            rank_analysis[h] = {
                "top5_avg": round(float(np.mean(t5)), 2),
                "top20_avg": round(float(np.mean(t20)), 2),
                "top5_win_rate": round(
                    sum(1 for r in t5 if r > 0) / len(t5) * 100, 1
                ),
                "top20_win_rate": round(
                    sum(1 for r in t20 if r > 0) / len(t20) * 100, 1
                ),
            }
    analysis["rank_analysis"] = rank_analysis

    # ── By market regime ──────────────────────────────────────────
    regime_picks: dict[str, list[dict]] = {}
    for day in daily_results:
        regime = day.get("regime", "unknown")
        for pick in day.get("picks", []):
            regime_picks.setdefault(regime, []).append(pick)

    by_regime: dict[str, dict] = {}
    for regime, rpicks in regime_picks.items():
        rh: dict = {}
        for h in FORWARD_HORIZONS:
            rets = _returns_for_horizon(rpicks, h)
            if rets:
                rh[h] = {
                    "n": len(rets),
                    "avg_return": round(float(np.mean(rets)), 2),
                    "win_rate": round(
                        sum(1 for r in rets if r > 0) / len(rets) * 100, 1
                    ),
                }
        by_regime[regime] = rh
    analysis["by_regime"] = by_regime

    # ── Factor quintile analysis ──────────────────────────────────
    analysis["factor_quintiles"] = _quintile_analysis(picks)

    return analysis


def _quintile_analysis(picks: list[dict]) -> dict:
    """Split picks into quintiles by each numeric factor, measure returns.

    Uses 5-day forward return as the measurement horizon.
    """
    factors = [
        ("rs_percentile", False),   # higher = expected better
        ("atr_compression", True),  # lower = tighter = expected better
        ("freshness_score", False), # higher = fresher catalyst
        ("vol_ratio_50d", False),   # higher = more volume interest
        ("hh_hl_pct", False),       # higher = better price structure
    ]

    horizon = 5
    results: dict = {}

    for factor_name, lower_is_better in factors:
        # Collect (factor_value, forward_return) pairs
        pairs: list[tuple[float, float]] = []
        for pick in picks:
            fv = pick["factors"].get(factor_name)
            ret = _get_return(pick, horizon)
            if fv is not None and ret is not None:
                pairs.append((float(fv), ret))

        if len(pairs) < 25:
            continue

        # Sort so Q1 = expected best
        pairs.sort(key=lambda x: x[0], reverse=(not lower_is_better))

        n = len(pairs)
        q_size = n // 5
        quintiles: dict = {}
        for q in range(5):
            lo = q * q_size
            hi = lo + q_size if q < 4 else n
            q_rets = [r for _, r in pairs[lo:hi]]
            quintiles[f"Q{q + 1}"] = {
                "n": len(q_rets),
                "avg_return": round(float(np.mean(q_rets)), 2),
                "win_rate": round(
                    sum(1 for r in q_rets if r > 0) / len(q_rets) * 100, 1
                ),
            }

        results[factor_name] = {
            "quintiles": quintiles,
            "note": (
                f"Q1 = {'lowest' if lower_is_better else 'highest'} "
                f"{factor_name} (expected best)"
            ),
        }

    return results


# ── Terminal output ───────────────────────────────────────────────────────


def _print_summary(analysis: dict) -> None:
    """Print formatted backtest summary."""
    print()
    print("  " + "=" * 50)
    print("  BACKTEST RESULTS")
    print("  " + "=" * 50)

    # Overall returns
    ph = analysis.get("per_horizon", {})
    if ph:
        print()
        print("  Overall Returns (Top 20 picks per day):")
        print("  " + "-" * 48)
        print(
            f"  {'Horizon':>8} {'N':>6} {'Win%':>7} {'Avg':>8} "
            f"{'Median':>8} {'Best':>8} {'Worst':>8}"
        )
        for h in FORWARD_HORIZONS:
            s = ph.get(h) or ph.get(str(h))
            if s:
                print(
                    f"  {h:>5}d {s['n']:>6} {s['win_rate']:>6.1f}% "
                    f"{s['avg_return']:>+7.2f}% {s['median_return']:>+7.2f}% "
                    f"{s['best']:>+7.2f}% {s['worst']:>+7.2f}%"
                )

    # Top 5 vs Top 20
    ra = analysis.get("rank_analysis", {})
    if ra:
        print()
        print("  Top 5 vs Top 20:")
        print("  " + "-" * 48)
        print(
            f"  {'Horizon':>8} {'Top5 Avg':>10} {'Top20 Avg':>10} "
            f"{'Top5 Win%':>10} {'Top20 Win%':>11}"
        )
        for h in FORWARD_HORIZONS:
            s = ra.get(h) or ra.get(str(h))
            if s:
                print(
                    f"  {h:>5}d {s['top5_avg']:>+9.2f}% "
                    f"{s['top20_avg']:>+9.2f}% "
                    f"{s['top5_win_rate']:>9.1f}% "
                    f"{s['top20_win_rate']:>10.1f}%"
                )

    # Regime breakdown
    br = analysis.get("by_regime", {})
    if br:
        print()
        print("  By Market Regime (5-day return):")
        print("  " + "-" * 48)
        for regime, horizons in sorted(br.items()):
            s = horizons.get(5) or horizons.get("5")
            if s:
                print(
                    f"  {regime:>12}: avg {s['avg_return']:+.2f}%, "
                    f"win {s['win_rate']:.1f}% (n={s['n']})"
                )

    # Factor quintiles
    fq = analysis.get("factor_quintiles", {})
    if fq:
        print()
        print("  Factor Quintile Analysis (5-day returns):")
        print("  " + "-" * 48)
        for factor, data in fq.items():
            qs = data.get("quintiles", {})
            q1 = qs.get("Q1", {})
            q5 = qs.get("Q5", {})
            if q1 and q5:
                spread = q1.get("avg_return", 0) - q5.get("avg_return", 0)
                print(
                    f"  {factor:>20}: Q1 {q1['avg_return']:+.2f}% "
                    f"-> Q5 {q5['avg_return']:+.2f}%  "
                    f"(spread {spread:+.2f}%)"
                )
