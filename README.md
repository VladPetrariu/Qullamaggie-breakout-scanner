<p align="center">
  <h1 align="center">Qullamaggie Breakout Scanner</h1>
  <p align="center">
    A free, open-source pre-market stock scanner that finds momentum breakout setups<br>across the entire NYSE + NASDAQ universe — based on <a href="https://twitter.com/Qullamaggie">Kristjan Kullamägi's</a> methodology.
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/data-yfinance_(free)-green" alt="Free data">
    <img src="https://img.shields.io/badge/API_keys-none_required-brightgreen" alt="No API keys">
    <img src="https://img.shields.io/badge/output-HTML_dashboard-orange" alt="HTML output">
  </p>
</p>

---

Scans **~2,300 liquid stocks** every morning, computes **6 factor categories** across each one, and ranks them into a self-contained dark-mode HTML dashboard. No paid data feeds, no API keys, no server — just run it and open the output.

> **Philosophy:** The scanner organizes the homework — *you* decide every trade. Raw values only, no composite scores, no buy/sell signals.

## Features

- **Full universe coverage** — fetches every NYSE/NASDAQ ticker from SEC EDGAR, filters to liquid names ($5+ price, 500K+ daily volume)
- **Market context gate** — breadth indicators, VIX, breakout follow-through rate; risk-off regime suppresses all output
- **6 factor categories** computed per stock:

| Factor | What it measures |
|--------|-----------------|
| **Catalyst** | Volume spike detection with half-life freshness scoring |
| **Volume** | Daily pace vs 50-day avg, flag volume contraction, ABR distance to level |
| **Consolidation** | EMA stack, price structure (HH/HL), candle quality, pole+flag, ATR compression |
| **Relative Strength** | ATR-normalized percentile vs universe, 5-day direction, vs SPY & sector ETF |
| **Breakout Level** | ATH > multi-year > 52-week > prior resistance classification |
| **Weekly Confluence** | Daily + weekly coiling/breakout simultaneously |

- **3-tier ranking** — catalyst freshness → factor quality count → ABR distance to level
- **Dark-mode dashboard** — filterable by sector, EMA stack, catalyst status, breakout level
- **Clickable tickers** — each stock links directly to its TradingView chart
- **Historical comparison** — NEW badges and rank change arrows vs prior day's scan
- **Offline & private** — everything runs locally, no data leaves your machine

## Quick Start

```bash
git clone https://github.com/VladPetrariu/Qullamaggie-breakout-scanner.git
cd Qullamaggie-breakout-scanner
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m scanner
```

| Run | Time | Notes |
|-----|------|-------|
| First run | ~4 min | Downloads 1 year of daily data for 7,000+ tickers |
| Cached run | ~12 sec | Uses local parquet cache, refreshes every 16 hours |

The dashboard opens automatically at `scans/scan_YYYY-MM-DD.html`.

## Dashboard

The output is a single self-contained HTML file (no dependencies, works offline):

- **Market context banner** — regime classification with breadth indicators
- **Stock cards** — every factor value displayed, color-coded by quality
- **Filters** — search by ticker/name, filter by EMA stack, catalyst, breakout level, sector
- **Sort** — by any factor (RS percentile, ATR compression, volume pace, catalyst freshness, etc.)
- **Keyboard shortcut** — press `/` to focus the search bar

## How It Works

```
SEC EDGAR tickers → yfinance OHLCV download → price/volume filter
                                                      ↓
                                              Market Context (gate)
                                                      ↓
                                          ┌───────────────────────┐
                                          │  Factor Analysis      │
                                          │  • Catalyst           │
                                          │  • Volume             │
                                          │  • Consolidation      │
                                          │  • Relative Strength  │
                                          │  • Breakout Level     │
                                          │  • Weekly Confluence  │
                                          └───────────────────────┘
                                                      ↓
                                            3-tier ranking sort
                                                      ↓
                                        HTML dashboard + JSON export
```

## Project Structure

```
scanner/
├── __main__.py              # 8-step pipeline orchestrator
├── config.py                # All thresholds and constants (single source of truth)
├── cache.py                 # Parquet + JSON file cache with TTL
├── universe.py              # SEC EDGAR ticker fetch + price/volume filter
├── data.py                  # yfinance batch downloader (500/chunk)
├── profile.py               # Float, short interest, sector (threaded)
├── ranking.py               # 3-tier watchlist sort
├── dashboard.py             # Jinja2 HTML generation + historical comparison
└── factors/
    ├── market_context.py    # 5 breadth indicators → regime classification
    ├── catalyst.py          # Volume spike proxy → tier → freshness scoring
    ├── volume.py            # Volume pace, ABR distance, flag volume pattern
    ├── consolidation.py     # EMA, HH/HL, candle quality, pole+flag, ATR compression
    ├── relative_strength.py # ATR-normalized RS vs universe + sector ETF
    ├── breakout_level.py    # ATH / multi-year / 52wk / prior resistance
    └── weekly.py            # Weekly resampling → coiling/breakout confluence
```

## Configuration

All thresholds live in [`scanner/config.py`](scanner/config.py). Key parameters:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `MIN_PRICE` | $5 | Minimum stock price |
| `MIN_AVG_VOLUME` | 500K | Minimum 20-day average volume |
| `VOLUME_SPIKE_THRESHOLD` | 3.0x | Volume multiple to detect catalysts |
| `EMA_PERIODS` | 10, 20, 50 | EMA stack periods |
| `CACHE_PRICES_TTL_HOURS` | 16 | Hours before price data refreshes |

## Data Sources

Everything is free — no API keys, no subscriptions:

| Data | Source |
|------|--------|
| Ticker universe | [SEC EDGAR](https://www.sec.gov/files/company_tickers_exchange.json) |
| Price & volume | [yfinance](https://github.com/ranaroussi/yfinance) (Yahoo Finance) |
| Float, short interest, sector | yfinance `Ticker.info` |

## Requirements

- Python 3.10+
- ~200MB disk space for cached data
- Internet connection (for data download only — dashboard works offline)

## Limitations

- **End-of-day data only** — yfinance provides daily bars, not intraday. Use this for pre-market watchlist building, not live entries
- **Catalyst detection is approximate** — volume spikes are a proxy for actual news events (earnings, FDA, contracts)
- **No backtesting** — this is a scanner, not a trading system
- **yfinance rate limits** — first run downloads ~7,000 tickers; occasional throttling is normal

## Background

This scanner implements the screening methodology described by [Kristjan Kullamägi (Qullamaggie)](https://twitter.com/Qullamaggie), a Swedish trader known for turning a small account into tens of millions trading momentum breakouts. The core idea: find stocks consolidating after a strong move, near a significant resistance level, with relative strength vs the market — then watch for the breakout with volume confirmation.

The flowchart defining the full pipeline logic is included in the repo.

## License

MIT
