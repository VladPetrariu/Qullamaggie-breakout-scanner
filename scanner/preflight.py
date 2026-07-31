"""Data-integrity preflight gate (step 2.5 of the pipeline).

The live era exposed two silent failure modes in the daily download:
benchmarks (SPY on 17 of 35 days) vanish from throttled batches, and
whole swaths of the universe arrive without the prior session's bar —
which then flows straight into stale signals. Because download_prices
caches by date, daily_run.sh's retry loop alone can never repair a bad
download: it just re-reads the poisoned parquet. The gate re-downloads
(force=True bypasses the cache) and, if the data still fails, refuses
to emit signals rather than trade on stale prices.

Three checks:
- freshness: benchmarks and >=90% of downloaded stock tickers carry the
  prior NYSE session's bar;
- completeness: the download contains at least half of the requested
  universe (throttling that drops whole 500-ticker chunks would
  otherwise shrink the freshness denominator and pass at 100%);
- unscheduled-closure fallback: when NOBODY has the prior session's bar
  (benchmarks included), that session was almost certainly an
  unscheduled closure (e.g. a mourning day) rather than a bad download
  — fall back one session instead of hard-failing a healthy day.
"""

from __future__ import annotations

from datetime import date as dt_date

import pandas as pd

from .config import (
    BENCHMARK_TICKERS,
    PREFLIGHT_BENCHMARKS,
    PREFLIGHT_MIN_COVERAGE_PCT,
    PREFLIGHT_MIN_UNIVERSE_FRACTION,
)
from .market_calendar import previous_trading_day


def _session_coverage(price_data: dict[str, pd.DataFrame], session: dt_date) -> dict:
    ts = pd.Timestamp(session)

    def has_bar(ticker: str) -> bool:
        df = price_data.get(ticker)
        if df is None or df.empty:
            return False
        return ts in pd.DatetimeIndex(df.index).normalize()

    missing_benchmarks = [b for b in PREFLIGHT_BENCHMARKS if not has_bar(b)]
    stock_tickers = [t for t in price_data if t not in BENCHMARK_TICKERS]
    with_bar = sum(1 for t in stock_tickers if has_bar(t))
    coverage_pct = (with_bar / len(stock_tickers) * 100) if stock_tickers else 0.0
    return {
        "missing_benchmarks": missing_benchmarks,
        "coverage_pct": coverage_pct,
        "n_tickers": len(stock_tickers),
        "n_with_bar": with_bar,
    }


def check_price_data(
    price_data: dict[str, pd.DataFrame],
    scan_date: dt_date,
    *,
    universe: list[str] | None = None,
    min_coverage_pct: float = PREFLIGHT_MIN_COVERAGE_PCT,
) -> dict:
    """Verify the download is fresh and complete enough to trade on."""
    prior = previous_trading_day(scan_date)
    cov = _session_coverage(price_data, prior)
    note = None

    fresh_ok = not cov["missing_benchmarks"] and cov["coverage_pct"] >= min_coverage_pct

    if (
        not fresh_ok
        and cov["coverage_pct"] < 2.0
        and len(cov["missing_benchmarks"]) == len(PREFLIGHT_BENCHMARKS)
    ):
        # Nobody at all has the prior session's bar — a bad download still
        # shows partial coverage, so this pattern means the session likely
        # never traded (unscheduled closure the rule-based calendar can't
        # know about, e.g. NYSE's 2025-01-09 mourning day).
        prior2 = previous_trading_day(prior)
        cov2 = _session_coverage(price_data, prior2)
        if not cov2["missing_benchmarks"] and cov2["coverage_pct"] >= min_coverage_pct:
            note = (
                f"no bars anywhere for {prior.isoformat()} — treating it as an "
                f"unscheduled market closure and checking {prior2.isoformat()}"
            )
            prior, cov = prior2, cov2
            fresh_ok = True

    universe_fraction = None
    complete_ok = True
    if universe:
        requested = [t for t in universe if t not in BENCHMARK_TICKERS]
        universe_fraction = cov["n_tickers"] / len(requested) if requested else 0.0
        complete_ok = universe_fraction >= PREFLIGHT_MIN_UNIVERSE_FRACTION

    return {
        "ok": fresh_ok and complete_ok,
        "prior_session": prior.isoformat(),
        "coverage_pct": round(cov["coverage_pct"], 1),
        "n_tickers": cov["n_tickers"],
        "n_with_prior_bar": cov["n_with_bar"],
        "missing_benchmarks": cov["missing_benchmarks"],
        "universe_fraction": (
            round(universe_fraction, 3) if universe_fraction is not None else None
        ),
        "note": note,
    }


def describe(result: dict) -> str:
    parts = [
        f"prior session {result['prior_session']}: "
        f"{result['coverage_pct']}% of {result['n_tickers']:,} tickers have its bar"
    ]
    if result["missing_benchmarks"]:
        parts.append(f"benchmarks missing it: {', '.join(result['missing_benchmarks'])}")
    if result.get("universe_fraction") is not None:
        parts.append(f"download holds {result['universe_fraction']:.0%} of the requested universe")
    if result.get("note"):
        parts.append(result["note"])
    return "; ".join(parts)
