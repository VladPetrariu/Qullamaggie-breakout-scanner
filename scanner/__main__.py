"""Entry point: python -m scanner"""

import sys
import time

from tqdm import tqdm

from .cache import Cache
from .config import CACHE_DIR, SCANS_DIR
from .dashboard import generate_dashboard, open_dashboard, save_scan_json
from .data import download_prices
from .factors.breakout_level import compute_breakout_level
from .factors.catalyst import compute_catalyst
from .factors.consolidation import compute_consolidation
from .factors.market_context import compute_market_context
from .factors.relative_strength import compute_universe_rs
from .factors.volume import compute_volume
from .factors.weekly import compute_weekly
from .profile import compute_abr, fetch_stock_profiles
from .ranking import rank_watchlist
from .universe import fetch_ticker_list, fetch_ticker_info, filter_universe

_REGIME_DISPLAY = {
    "favorable": "FAVORABLE  — full confidence",
    "mixed": "MIXED      — flag weak sectors",
    "caution": "CAUTION    — highest conviction only",
    "risk_off": "RISK OFF   — cash is the position",
}


def main():
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
        path = generate_dashboard(ctx, [], len(universe))
        open_dashboard(path)
        print(f"  Dashboard: {path}")
        return

    # ── 5. Relative strength ───────────────────────────────────────
    print()
    print("[5/8] Computing relative strength...")
    rs_data = compute_universe_rs(price_data, universe)
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

    # Merge profile data into watchlist
    for stock in watchlist:
        profile = profiles.get(stock["ticker"], {})
        stock["float_shares"] = profile.get("float_shares")
        stock["float_label"] = profile.get("float_label", "")
        stock["short_pct_float"] = profile.get("short_pct_float")
        stock["short_ratio"] = profile.get("short_ratio")
        stock["sector"] = profile.get("sector", "")
        stock["industry"] = profile.get("industry", "")

    # ── 8. Dashboard ───────────────────────────────────────────────
    print()
    print("[8/8] Generating dashboard...")
    json_path = save_scan_json(ctx, watchlist)
    html_path = generate_dashboard(ctx, watchlist, len(universe))
    print(f"  JSON: {json_path}")
    print(f"  HTML: {html_path}")

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


if __name__ == "__main__":
    main()
