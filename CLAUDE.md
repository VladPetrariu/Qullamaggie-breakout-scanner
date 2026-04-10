# Qullamaggie Breakout Scanner

Local Python stock momentum scanner. Run before market open, outputs HTML dashboard.

## How to run

```bash
source .venv/bin/activate
python -m scanner        # or: python scan.py
```

First run ~4 min (downloads data). Cached runs ~5 sec.

## Project structure

```
scanner/
├── __main__.py              # Entry point, orchestrates full 8-step pipeline
├── config.py                # All constants and thresholds
├── cache.py                 # File cache (parquet + JSON, TTL-based)
├── universe.py              # SEC EDGAR ticker fetch + price/volume filter
├── data.py                  # yfinance batch downloader (500/chunk)
├── profile.py               # ABR computation + yfinance float/SI/sector fetch
├── ranking.py               # Watchlist sorting (EMA stack -> RS -> ATR compression)
├── dashboard.py             # Jinja2 HTML generation + JSON export + browser open
└── factors/
    ├── market_context.py    # Breadth indicators, regime classification
    ├── relative_strength.py # ATR-normalized RS percentile + direction
    └── consolidation.py     # EMA, price structure, candles, pole, ATR compression
templates/
└── dashboard.html           # Self-contained dark-mode HTML (inline CSS/JS)
scans/                       # Output: scan_YYYY-MM-DD.html + .json
cache/                       # Cached price data (parquet) and ticker lists (JSON)
```

## Conventions

- Factor modules return plain dicts. Universe-wide factors (RS, market context) take `(price_data, universe)`. Per-stock factors (consolidation) take `(ticker, df)`.
- All thresholds and constants live in `config.py`.
- Cache keys are date-stamped (e.g. `prices_2026-04-10.parquet`).
- No composite scores — raw values only. Ranking sorts by them but the dashboard shows numbers, not signals.
- Universe source: SEC EDGAR `company_tickers_exchange.json`, filtered to NYSE + Nasdaq, 1-5 letter tickers.
- yfinance `period="1y"` returns ~250 days (not 252). Don't hardcode 252 as a minimum.

## See also

- `PLAN.md` — full build plan, current progress, known issues
- `~/Downloads/Qullamaggie Scanner Flowchart.html` — the original flowchart defining the pipeline
