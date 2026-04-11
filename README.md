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

<p align="center">
  <img width="1508" height="830" alt="Screenshot 2026-04-10 at 1 50 34 PM" src="https://github.com/user-attachments/assets/4ad51c8b-aa82-4cde-9155-b8bf13fbffde" />
</p>

<p align="center">
  <img width="1509" height="826" alt="Screenshot 2026-04-10 at 1 50 46 PM" src="https://github.com/user-attachments/assets/0fdab515-35fe-41a3-b64e-808c85d9157f" />
</p>

## High-Level Overview

**The stock market has ~7,000 stocks listed on the two major US exchanges (NYSE and NASDAQ).** Every day, some of those stocks are about to make big moves — breakouts — where the price suddenly jumps up after sitting still for a while. Traders who catch these moves early can make money.

The problem is finding them. You'd have to look at thousands of charts every morning before the market opens at 9:30 AM. Nobody has time for that.

**This scanner does that work for you.** It downloads price data for all ~7,000 stocks, filters down to ~2,300 that are liquid enough to trade, runs each one through a checklist of factors that indicate a breakout might be coming, ranks them, and shows you the top results in a visual dashboard.

### What the factors mean in plain English

- **Market regime** — Is the overall market healthy? If most stocks are falling, even good setups tend to fail. The scanner checks 5 health indicators and classifies the market as Favorable, Mixed, Caution, or Risk Off (don't trade at all).
- **Catalyst** — Did something happen to this stock recently? The scanner detects days where trading volume was 3x+ normal and scores how "fresh" the catalyst is.
- **Consolidation** — After a stock runs up, it often pauses and trades sideways (like a spring coiling). The tighter and cleaner that pause, the more likely the next breakout is explosive. The scanner measures how tight the range is, how clean the price action looks, and whether the moving averages are lined up.
- **Relative strength** — Is this stock stronger than most other stocks? If the market is flat but this stock is quietly rising, that's a sign of underlying demand.
- **Breakout level** — Where is the stock trying to break out? An all-time high is the strongest because there's nobody above wanting to sell. A 52-week high is decent. Old resistance is weaker.
- **Weekly confirmation** — Is the weekly chart also setting up, not just the daily? When both timeframes align, the move tends to be bigger.

### What you can do with the results

**If you trade stocks:**
- Run it every morning before market open
- Look through the top-ranked cards and their charts
- Pick the 3-5 best setups for your watchlist
- Use `python -m scanner --watch` during the day — it'll notify you when a stock approaches its breakout level
- Over time, the track record feature shows how well the scanner's top picks performed historically

**If you're a developer:**
- It's a full data pipeline project (API ingestion → computation → visualization)
- Demonstrates pandas, matplotlib, yfinance, Jinja2 templating, caching, threading

**What it does NOT do:** It does not tell you to buy or sell. It does not place trades. It does not guarantee profits. It organizes data so a human can make faster, more informed decisions.

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

- **Evidence-based ranking** — ATR compression (tightest bases first) → factor quality count → ABR distance to level
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

### Other modes

```bash
python -m scanner --watch      # Intraday monitor — polls prices, macOS alerts on breakout
python -m scanner --backtest   # Walk-forward backtest — validates rankings against historical data
```

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
├── ranking.py               # Evidence-based watchlist sort
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

## Backtesting & Results

The scanner includes a walk-forward backtesting engine (`--backtest` mode) that validates whether the ranking system actually predicts positive forward returns. For each trading day in the test period, it computes what the scanner *would have output* using only data available up to that day (no lookahead), then measures what happened next.

### Latest results (Oct 2025 -- Mar 2026, 120 trading days)

**Current ranking performance (top 20 picks per day, 2,400 total picks):**

| Horizon | Win Rate | Avg Return | Median Return |
|---------|----------|------------|---------------|
| 1 day | 46.2% | -0.11% | +0.00% |
| 3 day | 49.1% | -0.42% | +0.00% |
| 5 day | **51.4%** | -0.30% | **+0.05%** |
| 10 day | **53.0%** | -0.48% | **+0.14%** |

Win rate is above 50% and median return is positive at 5-day and 10-day horizons. Average returns are still slightly negative, pulled down by outlier losses (corporate events, delistings) that would be addressed by winsorization.

### How we got here: iterative backtesting

The ranking system was overhauled through three iterations, each validated by the walk-forward backtest:

| Version | What changed | 5d Win Rate | 5d Median |
|---------|-------------|-------------|-----------|
| v1 — Catalyst freshness first | Original ranking | 45.9% | -0.64% |
| v2 — ATR compression first (no gate) | Promoted tightest ATR stocks | 41.4% | -0.27% |
| v3 — ATR compression + quality gate | Required uptrend + RS + volume | **51.4%** | **+0.05%** |

**v1** revealed that catalyst freshness was anti-predictive (-4.84% quintile spread) while ATR compression was the strongest signal (+3.05%). **v2** naively made ATR compression the primary key, but this selected dead/illiquid stocks with zero volatility — 59% of picks had no uptrend. **v3** added a quality gate requiring stocks to have an uptrend (EMA stack), relative strength (RS >= 20), and actual trading volume before ATR compression takes effect.

### Current ranking system

The ranking applies these rules in order:

1. **Quality gate** — stock must have EMA stack (full/partial/weak), RS percentile >= 20, and volume ratio >= 0.1. Stocks failing any criteria sort last.
2. **ATR compression** (primary sort key) — tighter consolidation = higher rank. Strongest backtest predictor.
3. **Factor quality count** (secondary) — how many factors are in their "strong" range (10 factors checked). Anti-predictive factors removed.
4. **ABR distance to level** (tertiary) — closer to breakout level = higher rank.
5. **Penalties** — post-catalyst cooldown (fresh catalyst + loose ATR = penalty) and extension penalty (>2 ABR above breakout level).

### Remaining improvements

1. **Winsorize extreme returns** — cap outliers at +/-30% to exclude corporate events that distort averages
2. **SPY benchmark comparison** — measure whether picks outperform simply buying the index
3. **External data integration** — news sentiment APIs, earnings surprise data, and fresh short interest to improve catalyst quality classification

Full quintile breakdowns and methodology details are in [`test_results/`](test_results/).

## Limitations

- **End-of-day data only** — yfinance provides daily bars, not intraday. Use this for pre-market watchlist building, not live entries
- **Catalyst detection is approximate** — volume spikes are a proxy for actual news events (earnings, FDA, contracts)
- **Ranking has modest edge** — backtesting shows 51% win rate and positive median returns, but average returns still slightly negative due to outlier losses
- **yfinance rate limits** — first run downloads ~7,000 tickers; occasional throttling is normal

## Background

This scanner implements the screening methodology described by [Kristjan Kullamägi (Qullamaggie)](https://twitter.com/Qullamaggie), a Swedish trader known for turning a small account into tens of millions trading momentum breakouts. The core idea: find stocks consolidating after a strong move, near a significant resistance level, with relative strength vs the market — then watch for the breakout with volume confirmation.

The flowchart defining the full pipeline logic is included in the repo.

## License

MIT
