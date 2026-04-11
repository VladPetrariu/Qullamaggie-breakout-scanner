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

**What it does NOT do:** It does not guarantee profits. The scanner identifies setups with a statistically validated edge, but trading involves risk. An autonomous trading mode (paper account) is in development to validate real-world execution.

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

- **Evidence-based ranking** — quality count (multi-factor combos) → HH/HL price structure → ATR compression → ABR distance to level
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
python -m scanner --analyze    # Multi-factor combination analysis on saved backtest results
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

### Latest results (Mar 2025 -- Mar 2026, 250 trading days)

**Current ranking performance (top 20 picks per day, 4,840 total picks):**

| Horizon | Win Rate | W. Avg Return | Median Return |
|---------|----------|---------------|---------------|
| 1 day | 50.6% | +0.12% | +0.04% |
| 3 day | 51.2% | +0.17% | +0.09% |
| 5 day | **52.4%** | **+0.33%** | **+0.21%** |
| 10 day | **56.1%** | **+0.95%** | **+0.80%** |

Win rate above 50% at all horizons. Median and winsorized average returns positive across the board. The 5-day win rate of 52.4% over 4,840 picks has a z-score of 3.34 (p < 0.001) — statistically significant. The 10-day results are the strongest: **56.1% win rate with +0.80% median return**.

Top 5 ranked stocks outperform top 20 (10d winsorized avg: +1.15% vs +0.95%), confirming the ranking correctly identifies the best setups.

### How we got here: iterative backtesting

The ranking system was overhauled through five iterations, each validated by walk-forward backtest:

| Version | What changed | Period | 5d Win% | 5d Median | 10d Win% |
|---------|-------------|--------|---------|-----------|----------|
| v1 — Freshness-first | Original ranking | 6mo | 45.9% | -0.64% | -- |
| v2 — ATR-first (no gate) | Tightest ATR stocks first | 6mo | 41.4% | -0.27% | -- |
| v3 — ATR + quality gate | Required uptrend + RS + volume | 6mo | 51.4% | +0.05% | 53.0% |
| v4 — Phase 7 refinements | ATR floor, HH/HL double-weighted | 6mo | 51.2% | +0.05% | 52.9% |
| **v5 — Quality-first** | **Quality count primary, HH/HL secondary** | **12mo** | **52.4%** | **+0.21%** | **56.1%** |

**v1** revealed that catalyst freshness was anti-predictive. **v3** added a quality gate that flipped the scanner from harmful to useful. **v5** used multi-factor combination analysis (Phase 8) to discover that every top-performing factor combo includes HH/HL price structure, and ATR compression alone barely beats baseline — leading to the quality-first sort that produced the best results.

### Current ranking system

The ranking applies these rules in order:

1. **Quality gate** — stock must have EMA stack (full/partial/weak), RS percentile >= 20, and volume ratio >= 0.1. Stocks failing any criteria sort last.
2. **Factor quality count** (primary sort key) — how many factors are in their "strong" range (12 factors checked, HH/HL double-weighted). Multi-factor combos drive win rates.
3. **HH/HL price structure** (secondary) — higher percentage of higher-highs/higher-lows = higher rank. Strongest single predictor in combo analysis.
4. **ATR compression** (tertiary) — tighter consolidation = higher rank, floored at 0.3 to prevent stagnant stocks ranking first.
5. **ABR distance to level** (quaternary) — closer to breakout level = higher rank.
6. **Penalties** — post-catalyst cooldown (fresh catalyst + loose ATR = penalty) and extension penalty (>2 ABR above breakout level).

### What's next: AI analysis + autonomous trading

**Phase 9 (in progress):** AI-enhanced analysis using Claude to review each top stock's chart and factor profile. Identifies patterns and red flags that numerical factors miss (distribution patterns that score well on ATR compression, descending triangles near ATH). Acts as a quality filter between the scanner and trade execution.

**Phase 10 (planned):** Fully autonomous trading bot using Alpaca's paper trading API. The complete pipeline: scan → AI analysis → trade execution → result tracking → self-improvement. Every trade generates real data (fills, slippage, timing) that feeds back into the system. Paper account only until provably profitable over 100+ trades with consistent win rate across market regimes.

Full quintile breakdowns and methodology details are in [`test_results/`](test_results/).

## Limitations

- **End-of-day data only** — yfinance provides daily bars, not intraday. Use this for pre-market watchlist building, not live entries
- **Catalyst detection is approximate** — volume spikes are a proxy for actual news events (earnings, FDA, contracts)
- **Ranking has modest edge** — backtesting shows 52.4% win rate and positive median returns at all horizons, strongest at 10 days (56.1%)
- **yfinance rate limits** — first run downloads ~7,000 tickers; occasional throttling is normal

## Background

This scanner implements the screening methodology described by [Kristjan Kullamägi (Qullamaggie)](https://twitter.com/Qullamaggie), a Swedish trader known for turning a small account into tens of millions trading momentum breakouts. The core idea: find stocks consolidating after a strong move, near a significant resistance level, with relative strength vs the market — then watch for the breakout with volume confirmation.

The flowchart defining the full pipeline logic is included in the repo.

## License

MIT
