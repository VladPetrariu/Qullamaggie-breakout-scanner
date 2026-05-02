"""Entry point: python -m scanner"""

import sys
import time

from tqdm import tqdm

from .cache import Cache
from .charts import generate_charts_batch
from .config import CACHE_DIR, DEFAULT_ACCOUNT_EQUITY, SCANS_DIR
from .dashboard import compute_deltas, generate_dashboard, load_prior_scan, open_dashboard, save_scan_json
from .data import download_prices
from .factors.breakout_level import compute_breakout_level
from .factors.catalyst import compute_catalyst
from .factors.consolidation import compute_consolidation
from .factors.market_context import compute_market_context
from .factors.relative_strength import compute_sector_etf_returns, compute_universe_rs
from .factors.volume import compute_volume
from .factors.weekly import compute_weekly
from .profile import compute_abr, fetch_stock_profiles
from .ranking import rank_watchlist
from .signals import generate_signals, print_signals, save_signals
from .tracker import compute_track_record
from .universe import fetch_ticker_list, fetch_ticker_info, filter_universe

_REGIME_DISPLAY = {
    "favorable": "FAVORABLE  — full confidence",
    "mixed": "MIXED      — flag weak sectors",
    "caution": "CAUTION    — highest conviction only",
    "risk_off": "RISK OFF   — cash is the position",
}


def main(*, print_signals_to_terminal: bool = False, account_equity: float = DEFAULT_ACCOUNT_EQUITY):
    start = time.time()
    print()
    print("  Qullamaggie Breakout Scanner")
    print("  " + "=" * 40)
    print()

    cache = Cache(CACHE_DIR)
    SCANS_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Universe ────────────────────────────────────────────────
    print("[1/8] Fetching stock universe...")
    try:
        raw_tickers = fetch_ticker_list(cache)
    except RuntimeError as exc:
        print(f"  ERROR: {exc}")
        sys.exit(1)
    names = fetch_ticker_info(cache)
    print(f"  {len(raw_tickers):,} raw tickers from NYSE/NASDAQ")

    # ── 2. Price data ──────────────────────────────────────────────
    print()
    print("[2/8] Downloading price data...")
    price_data = download_prices(raw_tickers, cache)
    print(f"  Received data for {len(price_data):,} tickers")

    # ── 3. Filter ──────────────────────────────────────────────────
    print()
    print("[3/8] Filtering universe...")
    universe = filter_universe(raw_tickers, price_data)
    print(f"  {len(universe):,} stocks pass filters (price >= $5, avg vol >= 500K)")

    # ── 4. Market context ──────────────────────────────────────────
    print()
    print("[4/8] Market context...")
    ctx = compute_market_context(price_data, universe)
    _print_market_context(ctx)

    if ctx["regime"] == "risk_off":
        print()
        print("  Market is risk-off — suppressing all setups.")
        # Save an empty signals file so downstream bot logic always finds something
        empty_signals, summary = generate_signals([], "risk_off", price_data, account_equity)
        save_signals(empty_signals, summary)
        if print_signals_to_terminal:
            print_signals(empty_signals, summary)
        path = generate_dashboard(ctx, [], len(universe))
        open_dashboard(path)
        print(f"  Dashboard: {path}")
        return

    # ── 5. Relative strength ───────────────────────────────────────
    print()
    print("[5/8] Computing relative strength...")
    rs_data = compute_universe_rs(price_data, universe)
    sector_etf_returns = compute_sector_etf_returns(price_data)
    print(f"  RS computed for {len(rs_data):,} stocks")

    # ── 6. Factor analysis ──────────────────────────────────────
    print()
    print("[6/8] Analyzing setup factors...")
    watchlist = []
    for ticker in tqdm(universe, desc="  Scanning", unit="stock"):
        df = price_data.get(ticker)
        if df is None:
            continue

        consol = compute_consolidation(ticker, df)
        if consol is None:
            continue

        rs = rs_data.get(ticker)
        if rs is None:
            continue

        abr = compute_abr(df)
        name = names.get(ticker, "")

        # Phase 2 factors (optional — never gate on them)
        cat = compute_catalyst(ticker, df) or {}
        vol = compute_volume(ticker, df) or {}
        bl = compute_breakout_level(ticker, df) or {}
        wk = compute_weekly(ticker, df) or {}

        watchlist.append({
            "ticker": ticker,
            "name": name,
            "abr": abr,
            **rs,
            **consol,
            **cat,
            **vol,
            **bl,
            **wk,
        })

    print(f"  {len(watchlist):,} stocks with full factor data")

    # ── 7. Rank + enrich profiles ──────────────────────────────────
    print()
    print("[7/8] Ranking and enriching profiles...")
    watchlist = rank_watchlist(watchlist)

    # Fetch float/SI/sector for the top stocks only
    top_tickers = [s["ticker"] for s in watchlist[:50]]
    profiles = fetch_stock_profiles(top_tickers, cache)

    # Merge profile data + sector RS into watchlist
    spy_ret = sector_etf_returns.get("_spy")  # not present, computed below
    for stock in watchlist:
        profile = profiles.get(stock["ticker"], {})
        stock["float_shares"] = profile.get("float_shares")
        stock["float_label"] = profile.get("float_label", "")
        stock["short_pct_float"] = profile.get("short_pct_float")
        stock["short_ratio"] = profile.get("short_ratio")
        stock["sector"] = profile.get("sector", "")
        stock["industry"] = profile.get("industry", "")
        stock["next_earnings"] = profile.get("next_earnings")
        stock["earnings_days_ago"] = profile.get("earnings_days_ago")

        # Classify catalyst as earnings-related if spike happened near earnings
        earn_ago = stock.get("earnings_days_ago")
        cat_age = stock.get("catalyst_age")
        if stock.get("has_catalyst") and earn_ago is not None and cat_age is not None:
            if abs(earn_ago - cat_age) <= 2:
                stock["catalyst_type"] = "earnings"
            else:
                stock["catalyst_type"] = "other"
        elif stock.get("has_catalyst"):
            stock["catalyst_type"] = "unknown"
        else:
            stock["catalyst_type"] = None

        # Sector RS: compare vs sector ETF instead of SPY
        sector = stock["sector"]
        vs_spy = stock.get("vs_spy")
        etf_ret = sector_etf_returns.get(sector)
        if sector and vs_spy is not None and etf_ret is not None:
            # vs_spy = (stock_ret - spy_ret) * 100
            # vs_sector = (stock_ret - etf_ret) * 100
            #           = vs_spy + (spy_ret - etf_ret) * 100
            # We don't have spy_ret here, but we can get stock_ret from price data
            df = price_data.get(stock["ticker"])
            if df is not None and len(df) >= 21:
                stock_ret = float(df["Close"].pct_change(20).iloc[-1])
                vs_sector = round((stock_ret - etf_ret) * 100, 1)
                stock["vs_sector"] = vs_sector
                stock["vs_sector_label"] = (
                    "leading" if vs_sector >= 10 else
                    "neutral" if vs_sector >= -5 else
                    "laggard"
                )
            else:
                stock["vs_sector"] = None
                stock["vs_sector_label"] = "unknown"
        else:
            stock["vs_sector"] = None
            stock["vs_sector_label"] = "unknown"

    # ── 8. Charts + Dashboard ─────────────────────────────────────
    print()
    print("[8/8] Generating charts and dashboard...")
    charts = generate_charts_batch(watchlist, price_data, limit=50)
    print(f"  Generated {len(charts)} mini charts")

    # Attach chart URIs to watchlist entries
    for stock in watchlist:
        stock["chart_uri"] = charts.get(stock["ticker"])

    # Sector heat map — aggregate stats per sector from full watchlist
    sector_map: dict[str, dict] = {}
    for stock in watchlist:
        sec = stock.get("sector") or ""
        if not sec:
            continue
        if sec not in sector_map:
            sector_map[sec] = {"count": 0, "ath": 0, "catalyst": 0, "rs_sum": 0}
        sector_map[sec]["count"] += 1
        if stock.get("level_type") == "ath":
            sector_map[sec]["ath"] += 1
        if stock.get("has_catalyst"):
            sector_map[sec]["catalyst"] += 1
        sector_map[sec]["rs_sum"] += stock.get("rs_percentile", 50)

    sector_heat = []
    for sec, d in sorted(sector_map.items(), key=lambda x: -x[1]["ath"]):
        sector_heat.append({
            "sector": sec,
            "count": d["count"],
            "ath_count": d["ath"],
            "catalyst_count": d["catalyst"],
            "avg_rs": round(d["rs_sum"] / d["count"], 1) if d["count"] else 50,
        })

    track_record = compute_track_record(price_data)
    if track_record["per_horizon"]:
        print(f"  Track record from {track_record['total_scans']} prior scans:")
        for h, stats in sorted(track_record["per_horizon"].items()):
            print(f"    {h:>2}d: {stats['win_rate']}% win rate, avg {stats['avg_return']:+.1f}% (n={stats['n']})")

    prior = load_prior_scan()
    watchlist = compute_deltas(watchlist, prior)
    if prior:
        prior_count = len(prior.get("watchlist", []))
        new_count = sum(1 for s in watchlist if s.get("is_new"))
        print(f"  Compared with prior scan: {new_count} new entries (was {prior_count} stocks)")
    json_path = save_scan_json(ctx, watchlist)
    html_path = generate_dashboard(ctx, watchlist, len(universe), track_record, sector_heat)
    print(f"  JSON: {json_path}")
    print(f"  HTML: {html_path}")

    # Trade signals — always saved, printed only when --signals flag is set
    signals, sig_summary = generate_signals(
        watchlist, ctx["regime"], price_data, account_equity
    )
    sig_path = save_signals(signals, sig_summary)
    print(f"  Signals: {sig_path} ({len(signals)} issued)")
    if print_signals_to_terminal:
        print_signals(signals, sig_summary)

    elapsed = time.time() - start
    print()
    print(f"  Done in {elapsed:.1f}s — opening dashboard...")
    print()
    open_dashboard(html_path)


def _print_market_context(ctx):
    regime = ctx["regime"]
    print(f"  Regime: {_REGIME_DISPLAY.get(regime, regime)}")
    print(f"  % above 50 MA: {ctx['pct_above_50ma']}%")
    print(f"  % above 20 MA: {ctx['pct_above_20ma']}%")
    print(f"  52wk highs/lows: {ctx['new_highs']} / {ctx['new_lows']}"
          f" (ratio: {ctx['highs_lows_ratio']})")
    vix = ctx["vix_level"]
    vdir = ctx["vix_direction"]
    arrow = {"rising": "^", "falling": "v", "flat": "-", "unknown": "?"}.get(vdir, "?")
    if vix is not None:
        print(f"  VIX: {vix} ({arrow})")
    print(f"  Breakout follow-through: {ctx['breakout_followthrough']}%")


def _parse_equity_arg(argv: list[str]) -> float:
    """Pull --equity AMOUNT from argv. Default to DEFAULT_ACCOUNT_EQUITY."""
    if "--equity" not in argv:
        return DEFAULT_ACCOUNT_EQUITY
    i = argv.index("--equity")
    if i + 1 >= len(argv):
        print(f"  ERROR: --equity flag needs a value (e.g. --equity 25000)")
        sys.exit(1)
    try:
        return float(argv[i + 1])
    except ValueError:
        print(f"  ERROR: --equity value must be numeric, got '{argv[i + 1]}'")
        sys.exit(1)


if __name__ == "__main__":
    if "--watch" in sys.argv:
        from .watcher import watch
        watch()
    elif "--backtest-multi" in sys.argv:
        from .backtest import run_multi_window_backtest
        run_multi_window_backtest()
    elif "--backtest" in sys.argv:
        from .backtest import run_backtest
        run_backtest()
    elif "--analyze" in sys.argv:
        from .backtest import run_combination_analysis
        run_combination_analysis()
    elif "--exit-backtest" in sys.argv:
        from .exit_backtest import run_exit_backtest
        run_exit_backtest()
    else:
        equity = _parse_equity_arg(sys.argv)
        main(
            print_signals_to_terminal="--signals" in sys.argv,
            account_equity=equity,
        )
