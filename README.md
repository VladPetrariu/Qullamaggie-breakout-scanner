# Qullamaggie Breakout Scanner

A pre-market stock scanner based on Qullamaggie's breakout trading methodology. Scans the full NYSE/NASDAQ universe (~2,300 liquid stocks) and surfaces raw factor values in a self-contained HTML dashboard. No signals, no scores — you assess quality and decide every trade.

## What it does

1. Fetches all NYSE/NASDAQ tickers from SEC EDGAR
2. Downloads 1-year daily OHLCV data via yfinance
3. Filters to stocks above $5 with 500K+ avg daily volume
4. Computes market context (breadth, VIX, breakout follow-through rate)
5. Runs factor analysis on every stock:
   - **Catalyst detection** — volume spike proxy with freshness scoring
   - **Breakout volume** — volume pace, ABR distance to level, flag volume pattern
   - **Consolidation quality** — EMA interaction, price structure, candle quality, pole+flag, ATR compression
   - **Relative strength** — ATR-normalized percentile vs full universe, direction, vs SPY
   - **Breakout level** — ATH / multi-year / 52-week / prior resistance classification
   - **Weekly confirmation** — daily + weekly coiling/breakout confluence
6. Ranks by catalyst freshness → factor quality → ABR distance to level
7. Outputs a filterable dark-mode HTML dashboard

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m scanner
```

First run takes ~4 minutes (downloading price data). Cached runs take ~10-20 seconds.

Output goes to `scans/scan_YYYY-MM-DD.html` and opens automatically in your browser.

## Project structure

```
scanner/
├── __main__.py              # Entry point, orchestrates the pipeline
├── config.py                # All constants and thresholds
├── cache.py                 # File cache (parquet + JSON, TTL-based)
├── universe.py              # SEC EDGAR ticker fetch + price/volume filter
├── data.py                  # yfinance batch downloader
├── profile.py               # Float, short interest, sector (yfinance)
├── ranking.py               # 3-tier watchlist sort
├── dashboard.py             # Jinja2 HTML generation + JSON export
└── factors/
    ├── market_context.py    # Breadth indicators, regime classification
    ├── relative_strength.py # ATR-normalized RS percentile + direction
    ├── consolidation.py     # EMA, price structure, candles, pole, ATR compression
    ├── catalyst.py          # Volume spike detection + freshness scoring
    ├── volume.py            # Volume pace, ABR distance, flag volume
    ├── breakout_level.py    # Historical level significance
    └── weekly.py            # Weekly chart coiling/breakout confluence
templates/
└── dashboard.html           # Self-contained dark-mode HTML (inline CSS/JS)
scans/                       # Output (gitignored)
cache/                       # Cached data (gitignored)
```

## Data sources

All data comes from free sources — no paid API keys required:

- **Ticker universe**: SEC EDGAR `company_tickers_exchange.json`
- **Price data**: yfinance (Yahoo Finance)
- **Stock profiles**: yfinance `Ticker.info` (float, short interest, sector)

## Requirements

- Python 3.10+
- See `requirements.txt` for dependencies
