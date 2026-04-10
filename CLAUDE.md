# Qullamaggie Breakout Scanner

Local Python stock momentum scanner. Run before market open, outputs HTML dashboard.

## How to run

```bash
source .venv/bin/activate
python -m scanner              # full scan → opens dashboard
python -m scanner --watch      # intraday monitor → alerts on breakouts
```

First run ~4 min (downloads data). Cached runs ~14 sec.

## Project structure

```
scanner/
├── __main__.py              # Entry point, orchestrates 8-step pipeline
├── config.py                # All constants and thresholds
├── cache.py                 # File cache (parquet + JSON, TTL-based)
├── universe.py              # SEC EDGAR ticker fetch + price/volume filter
├── data.py                  # yfinance batch downloader (500/chunk)
├── profile.py               # Float/SI/sector/earnings fetch (threaded)
├── ranking.py               # 3-tier watchlist sort (catalyst → quality → ABR)
├── dashboard.py             # Jinja2 HTML generation + historical deltas
├── charts.py                # Matplotlib mini candlestick chart generator
├── tracker.py               # Historical result tracking (post-scan outcomes)
├── watcher.py               # Intraday --watch mode with price alerts
└── factors/
    ├── market_context.py    # Breadth indicators, regime classification
    ├── relative_strength.py # ATR-normalized RS percentile + sector ETF comparison
    ├── consolidation.py     # EMA, price structure, candles, pole, ATR compression
    ├── catalyst.py          # Volume spike detection + freshness scoring
    ├── volume.py            # Volume pace, ABR distance, flag volume pattern
    ├── breakout_level.py    # ATH/multi-year/52wk/prior resistance classification
    └── weekly.py            # Weekly chart coiling/breakout confluence
templates/
└── dashboard.html           # Self-contained dark-mode HTML (inline CSS/JS, legend overlay)
scans/                       # Output: scan_YYYY-MM-DD.html + .json
cache/                       # Cached price data (parquet) and ticker lists (JSON)
```

## Conventions

- Factor modules return plain dicts. Universe-wide factors (RS, market context) take `(price_data, universe)`. Per-stock factors (consolidation, catalyst, etc.) take `(ticker, df)`.
- All thresholds and constants live in `config.py`.
- Cache keys are date-stamped (e.g. `prices_2026-04-10.parquet`).
- No composite scores — raw values only. Ranking sorts by them but the dashboard shows numbers, not signals.
- Universe source: SEC EDGAR `company_tickers_exchange.json`, filtered to NYSE + Nasdaq, 1-5 letter tickers.
- yfinance `period="1y"` returns ~250 days (not 252). Don't hardcode 252 as a minimum.
- Profile/earnings data fetched via ThreadPoolExecutor (8 workers) for top 50 ranked stocks only.
- Charts generated as base64 PNGs embedded in the HTML (top 50 stocks).

## See also

- `PLAN.md` — full build plan, current progress, known issues
- `~/Downloads/Qullamaggie Scanner Flowchart.html` — the original flowchart defining the pipeline
