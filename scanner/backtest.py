"""Walk-forward backtesting engine.

For each trading day in the test window, computes what the scanner would have
output using only data available up to that day (no lookahead), then measures
forward returns at 1/3/5/10 day horizons.

Usage: python -m scanner --backtest
"""

from __future__ import annotations

import json
import time
from itertools import combinations
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
TEST_RESULTS_DIR = PROJECT_ROOT / "test_results"
BACKTEST_PERIOD = "3y"
TEST_WINDOW_DAYS = 250  # last ~12 months of trading days
TOP_N = 20
FORWARD_HORIZONS = [1, 3, 5, 10]
WINSORIZE_LIMIT = 30  # cap returns at +/-30% to reduce outlier distortion
MULTI_WINDOW_DAYS = 125  # ~6 months per window

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


# ── Shared data loading ───────────────────────────────────────────────────


def _load_backtest_data() -> tuple[list[str], dict[str, pd.DataFrame]] | None:
    """Download price data for backtesting. Returns (raw_tickers, price_data)."""
    cache = Cache(CACHE_DIR)
    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/4] Downloading 3 years of price data...")
    raw_tickers = fetch_ticker_list(cache)
    price_data = download_prices(raw_tickers, cache, period=BACKTEST_PERIOD)
    print(f"  Received data for {len(price_data):,} tickers")

    spy = price_data.get("SPY")
    if spy is None or len(spy) < 200:
        print("  ERROR: Not enough SPY data for backtest")
        return None

    return raw_tickers, price_data


# ── Public entry point ────────────────────────────────────────────────────


def run_backtest():
    """Run walk-forward backtest and print results."""
    start = time.time()
    print()
    print("  Qullamaggie Breakout Scanner — Backtest")
    print("  " + "=" * 45)
    print()

    result = _load_backtest_data()
    if result is None:
        return
    raw_tickers, price_data = result

    # ── 2. Determine test window ──────────────────────────────────
    spy = price_data["SPY"]
    all_dates = spy.index
    max_fwd = max(FORWARD_HORIZONS)
    # Reserve max_fwd days at the end for forward return measurement
    test_dates = all_dates[-(TEST_WINDOW_DAYS + max_fwd) : -max_fwd]

    print(
        f"  Testing {len(test_dates)} trading days: "
        f"{test_dates[0].date()} to {test_dates[-1].date()}"
    )

    # ── 3. Walk-forward simulation ────────────────────────────────
    daily_results = _run_simulation(
        raw_tickers, price_data, test_dates, label="Backtesting", use_checkpoint=True
    )

    # ── 4. Analyse results ────────────────────────────────────────
    print()
    print("[3/4] Analyzing results...")
    analysis = _analyze_results(daily_results, price_data)

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

    _print_summary(analysis)

    elapsed = time.time() - start
    print()
    print(f"  Done in {elapsed:.1f}s")
    print(f"  Results saved to {results_path}")
    print()


def run_multi_window_backtest():
    """Run backtest across 6 non-overlapping ~6-month windows covering 3 years.

    Downloads data once, then runs walk-forward simulation for each window.
    Saves per-window results and a cross-window comparison summary.
    """
    start = time.time()
    print()
    print("  Qullamaggie Breakout Scanner — Multi-Window Backtest")
    print("  " + "=" * 55)
    print()

    result = _load_backtest_data()
    if result is None:
        return
    raw_tickers, price_data = result

    spy = price_data["SPY"]
    all_dates = spy.index
    max_fwd = max(FORWARD_HORIZONS)

    # Need buffer: 50 days lookback at start, max_fwd days at end
    lookback_buffer = 50
    usable_start = lookback_buffer
    usable_end = len(all_dates) - max_fwd
    usable_dates = all_dates[usable_start:usable_end]

    # Split into 6 non-overlapping windows
    n_windows = 6
    window_size = len(usable_dates) // n_windows
    windows: list[tuple[str, pd.DatetimeIndex]] = []

    for i in range(n_windows):
        w_start = i * window_size
        w_end = (i + 1) * window_size if i < n_windows - 1 else len(usable_dates)
        w_dates = usable_dates[w_start:w_end]
        label = (
            f"{w_dates[0].strftime('%b %Y')} — {w_dates[-1].strftime('%b %Y')}"
        )
        windows.append((label, w_dates))

    print(f"  {len(usable_dates)} usable trading days split into {n_windows} windows:")
    for i, (label, w_dates) in enumerate(windows, 1):
        print(f"    Window {i}: {label} ({len(w_dates)} days)")
    print()

    # Run each window
    TEST_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    window_summaries: list[dict] = []

    for i, (label, w_dates) in enumerate(windows, 1):
        print()
        print(f"  {'=' * 55}")
        print(f"  Window {i}/{n_windows}: {label}")
        print(f"  {'=' * 55}")

        daily_results = _run_simulation(
            raw_tickers, price_data, w_dates, label=f"Window {i}"
        )

        analysis = _analyze_results(daily_results, price_data)

        # Save per-window results
        window_path = BACKTEST_DIR / f"multi_window_{i}.json"
        window_data = {
            "window": i,
            "label": label,
            "test_period": {
                "start": w_dates[0].strftime("%Y-%m-%d"),
                "end": w_dates[-1].strftime("%Y-%m-%d"),
                "trading_days": len(w_dates),
            },
            "daily_results": daily_results,
            "analysis": analysis,
        }
        with open(window_path, "w") as f:
            json.dump(window_data, f, indent=2, default=str)

        window_summaries.append({
            "window": i,
            "label": label,
            "days": len(w_dates),
            "analysis": analysis,
        })

        _print_summary(analysis)

    # Cross-window comparison
    _print_multi_window_comparison(window_summaries)

    # Save combined summary as markdown
    md_path = _save_multi_window_markdown(window_summaries)

    elapsed = time.time() - start
    print()
    print(f"  Done in {elapsed:.1f}s")
    print(f"  Summary saved to {md_path}")
    print()


def _print_multi_window_comparison(summaries: list[dict]) -> None:
    """Print cross-window comparison table."""
    print()
    print()
    print("  " + "=" * 70)
    print("  CROSS-WINDOW COMPARISON")
    print("  " + "=" * 70)

    # Per-horizon comparison
    for h in FORWARD_HORIZONS:
        print()
        print(f"  {h}-Day Returns:")
        print("  " + "-" * 70)
        print(
            f"  {'Window':>30} {'Days':>5} {'N':>6} {'Win%':>7} "
            f"{'W.Avg':>8} {'Median':>8}"
        )

        all_win_rates = []
        all_w_avgs = []
        all_medians = []

        for s in summaries:
            ph = s["analysis"].get("per_horizon", {})
            stats = ph.get(h) or ph.get(str(h))
            if stats:
                w_avg = stats.get("w_avg_return", stats["avg_return"])
                print(
                    f"  {s['label']:>30} {s['days']:>5} {stats['n']:>6} "
                    f"{stats['win_rate']:>6.1f}% {w_avg:>+7.2f}% "
                    f"{stats['median_return']:>+7.2f}%"
                )
                all_win_rates.append(stats["win_rate"])
                all_w_avgs.append(w_avg)
                all_medians.append(stats["median_return"])

        if all_win_rates:
            avg_wr = np.mean(all_win_rates)
            std_wr = np.std(all_win_rates)
            avg_wa = np.mean(all_w_avgs)
            avg_med = np.mean(all_medians)
            print(f"  {'':>30} {'':>5} {'':>6} {'─' * 28}")
            print(
                f"  {'Average':>30} {'':>5} {'':>6} "
                f"{avg_wr:>6.1f}% {avg_wa:>+7.2f}% {avg_med:>+7.2f}%"
            )
            print(
                f"  {'Std Dev':>30} {'':>5} {'':>6} "
                f"{std_wr:>6.1f}%"
            )

    # Regime breakdown per window
    print()
    print("  Regime Distribution:")
    print("  " + "-" * 70)
    print(f"  {'Window':>30} {'Favorable':>12} {'Mixed':>12} {'Caution':>12}")
    for s in summaries:
        br = s["analysis"].get("by_regime", {})
        fav = br.get("favorable", {}).get(5) or br.get("favorable", {}).get("5", {})
        mix = br.get("mixed", {}).get(5) or br.get("mixed", {}).get("5", {})
        cau = br.get("caution", {}).get(5) or br.get("caution", {}).get("5", {})
        fav_n = fav.get("n", 0) if fav else 0
        mix_n = mix.get("n", 0) if mix else 0
        cau_n = cau.get("n", 0) if cau else 0
        print(
            f"  {s['label']:>30} {fav_n:>12} {mix_n:>12} {cau_n:>12}"
        )


def _save_multi_window_markdown(summaries: list[dict]) -> Path:
    """Save cross-window comparison as markdown in test_results/."""
    from datetime import date as dt_date

    lines: list[str] = []
    today = dt_date.today().isoformat()
    lines.append(
        f"# Multi-Window Backtest Results — {today} (v5 quality-first ranking)"
    )
    lines.append("")
    lines.append(
        f"6 non-overlapping windows covering ~3 years of data. "
        f"Ranking: quality count → HH/HL → ATR → ABR distance."
    )
    lines.append("")

    # Summary table per horizon
    for h in FORWARD_HORIZONS:
        lines.append(f"## {h}-Day Forward Returns")
        lines.append("")
        lines.append(
            "| Window | Days | N | Win Rate | W.Avg | Median |"
        )
        lines.append("|--------|------|---|----------|-------|--------|")

        all_wr: list[float] = []
        all_wa: list[float] = []
        all_med: list[float] = []

        for s in summaries:
            ph = s["analysis"].get("per_horizon", {})
            stats = ph.get(h) or ph.get(str(h))
            if stats:
                w_avg = stats.get("w_avg_return", stats["avg_return"])
                lines.append(
                    f"| {s['label']} | {s['days']} | {stats['n']:,} | "
                    f"{stats['win_rate']:.1f}% | {w_avg:+.2f}% | "
                    f"{stats['median_return']:+.2f}% |"
                )
                all_wr.append(stats["win_rate"])
                all_wa.append(w_avg)
                all_med.append(stats["median_return"])

        if all_wr:
            lines.append(
                f"| **Average** | | | **{np.mean(all_wr):.1f}%** | "
                f"**{np.mean(all_wa):+.2f}%** | **{np.mean(all_med):+.2f}%** |"
            )
            lines.append(
                f"| **Std Dev** | | | {np.std(all_wr):.1f}% | "
                f"{np.std(all_wa):.2f}% | {np.std(all_med):.2f}% |"
            )
        lines.append("")

    # Regime distribution
    lines.append("## Regime Distribution (5-day pick counts)")
    lines.append("")
    lines.append("| Window | Favorable | Mixed | Caution |")
    lines.append("|--------|-----------|-------|---------|")
    for s in summaries:
        br = s["analysis"].get("by_regime", {})
        fav = br.get("favorable", {}).get(5) or br.get("favorable", {}).get("5", {})
        mix = br.get("mixed", {}).get(5) or br.get("mixed", {}).get("5", {})
        cau = br.get("caution", {}).get(5) or br.get("caution", {}).get("5", {})
        fav_n = fav.get("n", 0) if fav else 0
        mix_n = mix.get("n", 0) if mix else 0
        cau_n = cau.get("n", 0) if cau else 0
        lines.append(f"| {s['label']} | {fav_n} | {mix_n} | {cau_n} |")
    lines.append("")

    # Per-window regime win rates
    lines.append("## Regime Win Rates (5-day)")
    lines.append("")
    lines.append("| Window | Favorable | Mixed | Caution |")
    lines.append("|--------|-----------|-------|---------|")
    for s in summaries:
        br = s["analysis"].get("by_regime", {})
        parts = []
        for regime in ("favorable", "mixed", "caution"):
            rd = br.get(regime, {})
            stats = rd.get(5) or rd.get("5", {})
            if stats and stats.get("n", 0) >= 20:
                parts.append(f"{stats['win_rate']:.1f}%")
            else:
                parts.append("—")
        lines.append(f"| {s['label']} | {' | '.join(parts)} |")
    lines.append("")

    md_path = TEST_RESULTS_DIR / f"{today}_multi_window.md"
    md_path.write_text("\n".join(lines))
    return md_path


# ── Simulation core ──────────────────────────────────────────────────────


def _run_simulation(
    raw_tickers: list[str],
    price_data: dict[str, pd.DataFrame],
    test_dates: pd.DatetimeIndex,
    *,
    label: str = "Backtesting",
    use_checkpoint: bool = False,
) -> list[dict]:
    """Run walk-forward simulation over *test_dates*. Returns daily_results."""
    print()
    print("[2/4] Walk-forward simulation...")

    daily_results: list[dict] = []
    checkpoint_path = BACKTEST_DIR / "checkpoint.json"

    completed_dates: set[str] = set()
    if use_checkpoint and checkpoint_path.exists():
        try:
            with open(checkpoint_path) as f:
                saved = json.load(f)
            daily_results = saved.get("daily_results", [])
            completed_dates = {r["date"] for r in daily_results}
            print(f"  Resuming from checkpoint ({len(completed_dates)} days done)")
        except (json.JSONDecodeError, KeyError):
            pass

    for i, date in enumerate(tqdm(test_dates, desc=f"  {label}", unit="day")):
        date_str = date.strftime("%Y-%m-%d")
        if date_str in completed_dates:
            continue

        sliced = _slice_data(price_data, date)
        universe = _filter_universe_at(raw_tickers, sliced)
        if len(universe) < 50:
            daily_results.append(
                {"date": date_str, "regime": "insufficient_data", "picks": []}
            )
            continue

        ctx = compute_market_context(sliced, universe)
        regime = ctx["regime"]

        if regime == "risk_off":
            daily_results.append(
                {"date": date_str, "regime": "risk_off", "picks": []}
            )
            continue

        rs_data = compute_universe_rs(sliced, universe)

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

        watchlist = rank_watchlist(watchlist)
        top = watchlist[:TOP_N]

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

        if use_checkpoint and (i + 1) % 10 == 0:
            _save_checkpoint(checkpoint_path, daily_results)

    if use_checkpoint:
        checkpoint_path = BACKTEST_DIR / "checkpoint.json"
        checkpoint_path.unlink(missing_ok=True)

    return daily_results


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


def _winsorize(returns: list[float], limit: float = WINSORIZE_LIMIT) -> list[float]:
    """Clip returns to [-limit, +limit] to reduce outlier distortion."""
    return [max(-limit, min(limit, r)) for r in returns]


def _analyze_results(
    daily_results: list[dict],
    price_data: dict[str, pd.DataFrame] | None = None,
) -> dict:
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
            w_rets = _winsorize(rets)
            per_horizon[h] = {
                "n": len(rets),
                "win_rate": round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1),
                "avg_return": round(float(np.mean(rets)), 2),
                "median_return": round(float(np.median(rets)), 2),
                "best": round(max(rets), 2),
                "worst": round(min(rets), 2),
                "w_avg_return": round(float(np.mean(w_rets)), 2),
                "w_median_return": round(float(np.median(w_rets)), 2),
            }
    analysis["per_horizon"] = per_horizon

    # ── Top-5 vs Top-20 ──────────────────────────────────────────
    top5 = [p for p in picks if p["rank"] <= 5]
    rank_analysis = {}
    for h in FORWARD_HORIZONS:
        t5 = _returns_for_horizon(top5, h)
        t20 = _returns_for_horizon(picks, h)
        if t5 and t20:
            w_t5 = _winsorize(t5)
            w_t20 = _winsorize(t20)
            rank_analysis[h] = {
                "top5_avg": round(float(np.mean(t5)), 2),
                "top20_avg": round(float(np.mean(t20)), 2),
                "top5_win_rate": round(
                    sum(1 for r in t5 if r > 0) / len(t5) * 100, 1
                ),
                "top20_win_rate": round(
                    sum(1 for r in t20 if r > 0) / len(t20) * 100, 1
                ),
                "w_top5_avg": round(float(np.mean(w_t5)), 2),
                "w_top20_avg": round(float(np.mean(w_t20)), 2),
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

    # ── SPY benchmark ────────────────────────────────────────────
    if price_data and "SPY" in price_data:
        analysis["spy_benchmark"] = _compute_spy_benchmark(daily_results, price_data)

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
            w_rets = _winsorize(q_rets)
            quintiles[f"Q{q + 1}"] = {
                "n": len(q_rets),
                "avg_return": round(float(np.mean(w_rets)), 2),
                "raw_avg": round(float(np.mean(q_rets)), 2),
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


def _compute_spy_benchmark(
    daily_results: list[dict], price_data: dict[str, pd.DataFrame]
) -> dict:
    """Compute SPY returns over same horizons and excess returns vs picks."""
    result: dict = {}
    for h in FORWARD_HORIZONS:
        spy_rets: list[float] = []
        excess_rets: list[float] = []
        for day in daily_results:
            date = pd.Timestamp(day["date"])
            spy_fwd = _forward_returns(price_data, "SPY", date)
            spy_ret = spy_fwd.get(h)
            if spy_ret is None:
                continue
            spy_rets.append(spy_ret)
            for pick in day.get("picks", []):
                pick_ret = _get_return(pick, h)
                if pick_ret is not None:
                    excess_rets.append(pick_ret - spy_ret)

        if spy_rets and excess_rets:
            w_excess = _winsorize(excess_rets)
            result[h] = {
                "spy_avg": round(float(np.mean(spy_rets)), 2),
                "spy_median": round(float(np.median(spy_rets)), 2),
                "excess_avg": round(float(np.mean(excess_rets)), 2),
                "excess_median": round(float(np.median(excess_rets)), 2),
                "w_excess_avg": round(float(np.mean(w_excess)), 2),
                "w_excess_median": round(float(np.median(w_excess)), 2),
                "excess_win_rate": round(
                    sum(1 for r in excess_rets if r > 0)
                    / len(excess_rets)
                    * 100,
                    1,
                ),
            }
    return result


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
        print("  " + "-" * 68)
        print(
            f"  {'Horizon':>8} {'N':>6} {'Win%':>7} {'Avg':>8} "
            f"{'W.Avg':>8} {'Median':>8} {'Best':>8} {'Worst':>8}"
        )
        for h in FORWARD_HORIZONS:
            s = ph.get(h) or ph.get(str(h))
            if s:
                w_avg = s.get("w_avg_return", s["avg_return"])
                print(
                    f"  {h:>5}d {s['n']:>6} {s['win_rate']:>6.1f}% "
                    f"{s['avg_return']:>+7.2f}% {w_avg:>+7.2f}% "
                    f"{s['median_return']:>+7.2f}% "
                    f"{s['best']:>+7.2f}% {s['worst']:>+7.2f}%"
                )

    # Top 5 vs Top 20
    ra = analysis.get("rank_analysis", {})
    if ra:
        print()
        print("  Top 5 vs Top 20:")
        print("  " + "-" * 68)
        print(
            f"  {'Horizon':>8} {'Top5 Avg':>10} {'Top20 Avg':>10} "
            f"{'T5 W.Avg':>10} {'T20 W.Avg':>10} "
            f"{'Top5 Win%':>10} {'Top20 Win%':>11}"
        )
        for h in FORWARD_HORIZONS:
            s = ra.get(h) or ra.get(str(h))
            if s:
                w_t5 = s.get("w_top5_avg", s["top5_avg"])
                w_t20 = s.get("w_top20_avg", s["top20_avg"])
                print(
                    f"  {h:>5}d {s['top5_avg']:>+9.2f}% "
                    f"{s['top20_avg']:>+9.2f}% "
                    f"{w_t5:>+9.2f}% {w_t20:>+9.2f}% "
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

    # SPY benchmark
    spy = analysis.get("spy_benchmark", {})
    if spy:
        print()
        print("  SPY Benchmark (picks vs SPY, same horizons):")
        print("  " + "-" * 68)
        print(
            f"  {'Horizon':>8} {'SPY Avg':>9} {'Excess Avg':>11} "
            f"{'W.Excess':>10} {'Excess Med':>11} {'Beat SPY%':>10}"
        )
        for h in FORWARD_HORIZONS:
            s = spy.get(h) or spy.get(str(h))
            if s:
                w_exc = s.get("w_excess_avg", s["excess_avg"])
                print(
                    f"  {h:>5}d {s['spy_avg']:>+8.2f}% "
                    f"{s['excess_avg']:>+10.2f}% "
                    f"{w_exc:>+9.2f}% "
                    f"{s['excess_median']:>+10.2f}% "
                    f"{s['excess_win_rate']:>9.1f}%"
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


# ── Multi-factor combination analysis (Phase 8) ─────────────────────────

# Factor conditions for combination testing.
# Each maps a readable name to a function(factors_dict) -> bool.
_CONDITIONS = {
    "tight_atr": lambda f: (f.get("atr_compression") or 999) <= 0.5,
    "high_hh_hl": lambda f: (f.get("hh_hl_pct") or 0) >= 50,
    "high_vol": lambda f: (f.get("vol_ratio_50d") or 0) >= 1.5,
    "high_rs": lambda f: (f.get("rs_percentile") or 0) >= 70,
    "flag_dryup": lambda f: f.get("flag_vol_label") in ("dry_up", "contracting"),
    "has_pole": lambda f: f.get("has_pole") is True,
    "strong_ema": lambda f: f.get("ema_stack") in ("full", "partial"),
    "good_candle": lambda f: f.get("candle_label") in ("ideal", "ok"),
    "weekly_conf": lambda f: f.get("weekly_confluence")
    in ("max_confluence", "max_confirmation", "strong"),
    "ath_level": lambda f: f.get("level_type") in ("ath", "multi_year"),
    "not_fresh": lambda f: (f.get("freshness_score") or 0) <= 30,
    "rs_up": lambda f: (f.get("rs_direction") or 0) >= 3,
}

MIN_COMBO_PICKS = 50  # minimum sample size for statistical relevance


def run_combination_analysis():
    """Analyze factor combinations from saved backtest results.

    Phase 8 steps 44-45: tests all single/pair/trio factor combinations,
    measures win rate and returns, and breaks down by market regime.
    """
    print()
    print("  Multi-Factor Combination Analysis (Phase 8)")
    print("  " + "=" * 50)

    # ── Load saved results ────────────────────────────────────
    results_path = BACKTEST_DIR / "results.json"
    if not results_path.exists():
        print("  ERROR: No backtest results found. Run --backtest first.")
        return

    with open(results_path) as f:
        data = json.load(f)

    daily_results = data["daily_results"]

    # Flatten picks, attaching regime from the day level
    picks: list[dict] = []
    for day in daily_results:
        regime = day.get("regime", "unknown")
        for pick in day.get("picks", []):
            picks.append({**pick, "regime": regime})

    if not picks:
        print("  ERROR: No picks found in results.")
        return

    print(f"\n  Analyzing {len(picks):,} picks across {len(daily_results)} days")

    horizon = 5

    # ── Baseline ──────────────────────────────────────────────
    baseline = _combo_stats(picks, horizon)
    print(
        f"  Baseline: n={baseline['n']}, "
        f"win {baseline['win_rate']:.1f}%, "
        f"avg {baseline['avg']:+.2f}%, "
        f"med {baseline['median']:+.2f}%"
    )

    # ── Precompute condition masks as index sets ──────────────
    cond_names = sorted(_CONDITIONS.keys())
    mask_sets: dict[str, set[int]] = {}
    for name in cond_names:
        mask_sets[name] = {
            i
            for i, p in enumerate(picks)
            if _CONDITIONS[name](p.get("factors", {}))
        }

    # ── Test all singles, pairs, trios ────────────────────────
    print("\n  Testing combinations...")
    all_combos: list[dict] = []

    for size in (1, 2, 3):
        for combo in combinations(cond_names, size):
            idx = mask_sets[combo[0]]
            for c in combo[1:]:
                idx = idx & mask_sets[c]
            if len(idx) < MIN_COMBO_PICKS:
                continue
            matching = [picks[i] for i in idx]
            stats = _combo_stats(matching, horizon)
            all_combos.append({"combo": combo, **stats})

    all_combos.sort(key=lambda r: r["win_rate"], reverse=True)

    # ── Print singles ─────────────────────────────────────────
    singles = [r for r in all_combos if len(r["combo"]) == 1]
    print(f"\n  Single Factors ({len(singles)} with n>={MIN_COMBO_PICKS}):")
    print("  " + "-" * 58)
    print(f"  {'Factor':>18} {'N':>6} {'Win%':>7} {'Avg':>8} {'Median':>8}")
    for r in singles:
        print(
            f"  {r['combo'][0]:>18} {r['n']:>6} "
            f"{r['win_rate']:>6.1f}% {r['avg']:>+7.2f}% {r['median']:>+7.2f}%"
        )

    # ── Print top pairs ───────────────────────────────────────
    pairs = [r for r in all_combos if len(r["combo"]) == 2]
    print(f"\n  Top 25 Factor Pairs ({len(pairs)} tested):")
    print("  " + "-" * 70)
    print(f"  {'Combo':>35} {'N':>6} {'Win%':>7} {'Avg':>8} {'Median':>8}")
    for r in pairs[:25]:
        label = " + ".join(r["combo"])
        print(
            f"  {label:>35} {r['n']:>6} "
            f"{r['win_rate']:>6.1f}% {r['avg']:>+7.2f}% {r['median']:>+7.2f}%"
        )

    # ── Print top trios ───────────────────────────────────────
    trios = [r for r in all_combos if len(r["combo"]) == 3]
    print(f"\n  Top 25 Factor Trios ({len(trios)} tested):")
    print("  " + "-" * 80)
    print(f"  {'Combo':>50} {'N':>6} {'Win%':>7} {'Avg':>8} {'Median':>8}")
    for r in trios[:25]:
        label = " + ".join(r["combo"])
        print(
            f"  {label:>50} {r['n']:>6} "
            f"{r['win_rate']:>6.1f}% {r['avg']:>+7.2f}% {r['median']:>+7.2f}%"
        )

    # ── Regime breakdown for top 10 overall (Step 45) ─────────
    print("\n  Regime Breakdown — Top 10 Combos:")
    print("  " + "-" * 80)
    for i, r in enumerate(all_combos[:10], 1):
        label = " + ".join(r["combo"])
        print(
            f"\n  #{i}: {label}  "
            f"(n={r['n']}, win {r['win_rate']:.1f}%, "
            f"avg {r['avg']:+.2f}%, med {r['median']:+.2f}%)"
        )
        idx = mask_sets[r["combo"][0]]
        for c in r["combo"][1:]:
            idx = idx & mask_sets[c]
        matching = [picks[j] for j in idx]
        regime_stats = _combo_regime_stats(matching, horizon)
        for regime in sorted(regime_stats):
            rs = regime_stats[regime]
            print(
                f"      {regime:>12}: n={rs['n']:>4}, "
                f"win {rs['win_rate']:>5.1f}%, avg {rs['avg']:+.2f}%"
            )

    # ── Best combo per regime (Step 45) ───────────────────────
    regimes = sorted({p["regime"] for p in picks if p.get("picks") is not None or True})
    regime_picks: dict[str, list[int]] = {}
    for i, p in enumerate(picks):
        regime_picks.setdefault(p["regime"], []).append(i)

    print("\n  Best Combo per Regime:")
    print("  " + "-" * 80)
    for regime in sorted(regime_picks):
        if regime in ("risk_off", "insufficient_data"):
            continue
        r_indices = set(regime_picks[regime])
        if len(r_indices) < MIN_COMBO_PICKS:
            continue

        best: dict | None = None
        for size in (1, 2, 3):
            for combo in combinations(cond_names, size):
                idx = r_indices & mask_sets[combo[0]]
                for c in combo[1:]:
                    idx = idx & mask_sets[c]
                if len(idx) < 30:
                    continue
                matching = [picks[j] for j in idx]
                stats = _combo_stats(matching, horizon)
                if best is None or stats["win_rate"] > best["win_rate"]:
                    best = {"combo": combo, **stats}

        if best:
            label = " + ".join(best["combo"])
            total = len(r_indices)
            print(
                f"  {regime:>12}: {label:>40}  "
                f"n={best['n']}/{total}, "
                f"win {best['win_rate']:.1f}%, "
                f"avg {best['avg']:+.2f}%"
            )

    # ── Save results ──────────────────────────────────────────
    save_path = PROJECT_ROOT / "test_results" / "phase8_combinations.json"
    save_data = {
        "baseline": baseline,
        "conditions_tested": cond_names,
        "min_picks": MIN_COMBO_PICKS,
        "horizon": horizon,
        "singles": [
            {"combo": list(r["combo"]), **{k: v for k, v in r.items() if k != "combo"}}
            for r in singles
        ],
        "top_pairs": [
            {"combo": list(r["combo"]), **{k: v for k, v in r.items() if k != "combo"}}
            for r in pairs[:30]
        ],
        "top_trios": [
            {"combo": list(r["combo"]), **{k: v for k, v in r.items() if k != "combo"}}
            for r in trios[:30]
        ],
    }
    with open(save_path, "w") as f:
        json.dump(save_data, f, indent=2)

    print(f"\n  Results saved to {save_path}")
    print()


def _combo_stats(picks: list[dict], horizon: int) -> dict:
    """Compute win rate, avg, and median for a filtered set of picks."""
    rets = _returns_for_horizon(picks, horizon)
    if not rets:
        return {"n": 0, "win_rate": 0.0, "avg": 0.0, "median": 0.0}
    w_rets = _winsorize(rets)
    return {
        "n": len(rets),
        "win_rate": round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1),
        "avg": round(float(np.mean(w_rets)), 2),
        "median": round(float(np.median(rets)), 2),
    }


def _combo_regime_stats(picks: list[dict], horizon: int) -> dict[str, dict]:
    """Break down combo stats by market regime."""
    by_regime: dict[str, list[dict]] = {}
    for p in picks:
        by_regime.setdefault(p.get("regime", "unknown"), []).append(p)

    result: dict[str, dict] = {}
    for regime, rpicks in by_regime.items():
        rets = _returns_for_horizon(rpicks, horizon)
        if rets:
            w_rets = _winsorize(rets)
            result[regime] = {
                "n": len(rets),
                "win_rate": round(
                    sum(1 for r in rets if r > 0) / len(rets) * 100, 1
                ),
                "avg": round(float(np.mean(w_rets)), 2),
            }
    return result
