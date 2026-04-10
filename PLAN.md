# Implementation Plan

## What and why

A pre-market stock scanner based on Qullamaggie's breakout trading methodology. Replaces manually reviewing thousands of charts each morning by computing factor scores across the full NYSE/NASDAQ universe and surfacing raw values in an HTML dashboard. The user decides every trade — the scanner just organizes the data.

The flowchart at `~/Downloads/Qullamaggie Scanner Flowchart.html` defines the full pipeline.

## Pipeline (from flowchart)

| Stage | Role |
|-------|------|
| Market Context (gate) | Kill switch — risk-off suppresses all output |
| Catalyst Context (sort key) | Macro (3 tiers with halflife decay) + company catalysts (earnings, 8-K) |
| B — Breakout Volume (most important factor) | Volume pace, ABR distance to level, flag volume pattern |
| A — Consolidation (second most important) | Price structure (HH/HL), candle quality, EMA interaction, pole+flag, duration |
| C — Relative Strength | ATR-normalized percentile vs universe, 5-day direction, vs sector ETF |
| D — Breakout Level | ATH > multi-year > 52wk high > prior resistance |
| E — Weekly Confirmation (amplifier) | Daily+weekly coiling/breaking simultaneously |
| Stock Profile (always shown) | Float, short interest, 21-day ABR |
| Watchlist Sort | Catalyst freshness → factor quality count → ABR distance to level |

## Build phases and progress

### Phase 1 — MVP

| Step | Module | Status |
|------|--------|--------|
| 1 | Project skeleton (`setup.py`, `requirements.txt`, entry points) | DONE |
| 2 | `config.py` — constants, thresholds, sector ETF map | DONE |
| 3 | `cache.py` — parquet/JSON file cache with TTL | DONE |
| 4 | `universe.py` — SEC EDGAR ticker fetch + price/volume filter | DONE |
| 5 | `data.py` — yfinance batch downloader with caching | DONE |
| 6 | `factors/market_context.py` — 5 breadth indicators, regime classification | DONE |
| 7 | `factors/relative_strength.py` — RS percentile, direction, vs SPY | DONE |
| 8 | `factors/consolidation.py` — EMA, price structure, candles, pole, ATR compression | DONE |
| 9 | `profile.py` — float, short interest, 21-day ABR | DONE |
| 10 | `ranking.py` — basic sort (EMA stack → RS percentile → ATR compression) | DONE |
| 11 | `dashboard.py` + `templates/dashboard.html` — HTML output with cards, filters | DONE |
| 12 | `__main__.py` wiring — connect ranking + dashboard, save JSON, open browser | DONE |

### Phase 2 — Full Factor Suite

| Step | Module | Status |
|------|--------|--------|
| 13 | `factors/catalyst.py` — volume spike proxy, tier classification, freshness scoring | DONE |
| 14 | `factors/consolidation.py` refinement — tune detection logic with real examples | DONE |
| 15 | `factors/volume.py` — volume pace vs 50-day, ABR distance, flag volume pattern | DONE |
| 16 | `factors/breakout_level.py` — ATH/multi-year/52wk/prior resistance classification | DONE |
| 17 | `factors/weekly.py` — weekly chart coiling/breakout detection | DONE |
| 18 | `ranking.py` upgrade — full 3-tier: catalyst freshness → factor quality → ABR distance | DONE |

### Phase 3 — Polish

| Step | What | Status |
|------|------|--------|
| 19 | Dashboard UX: clickable tickers (TradingView), catalyst/level filters, keyboard shortcut, mobile | DONE |
| 20 | Performance: parallel profile fetch (8x faster), weekly resampling optimization | DONE |
| 21 | Historical comparison: load prior scan, NEW badges, rank change arrows | DONE |

### Phase 4 — Precision & Effectiveness

| Step | What | Status |
|------|------|--------|
| 22 | Mini charts: inline candlestick sparklines on each dashboard card (matplotlib) | DONE |
| 23 | Earnings date integration: yfinance calendar → catalyst classification + next earnings | DONE |
| 24 | Historical result tracking: measure post-scan outcomes at 1/3/5/10 day horizons | DONE |
| 25 | Sector rotation overlay: sector heat map showing RS leaders, ATH density | DONE |
| 26 | Intraday price alerts: `--watch` mode, polls prices, macOS notifications on breakout | DONE |

## Where we are now

**All phases complete (steps 1-26).** Full feature set:
- Full factor suite (catalyst, volume, consolidation, RS, breakout level, weekly)
- Sector RS comparison (vs per-sector ETF)
- 3-tier ranking with 11 quality factors
- Dashboard: mini candlestick charts, sector heat map, track record, historical deltas
- Earnings date integration with catalyst classification
- Intraday `--watch` mode with macOS notifications on breakout
- ~14 seconds cached, ~4 min first run

## Known issues

- ~~**Sector RS (C3)**: Compares vs SPY, not per-sector ETF.~~ FIXED — now computes vs sector ETF for stocks with profile data.
- **yfinance data length**: `period="1y"` returns ~250 days, not 252. All code uses available data length, not hardcoded 252. (Not a bug — documented behaviour.)

## Data source adaptations (yfinance free-data limitations)

| Flowchart concept | What we do instead |
|-------------------|--------------------|
| B1 Volume pace (5-min intraday bars) | Daily volume vs 50-day average |
| B2 ABR from open to entry (intraday) | Distance from close to breakout level in ABR units |
| Catalyst detection (news/8-K feed) | Earnings dates from yfinance + volume spike proxy (>3x avg) |
| Float / Short interest | `yfinance Ticker.info` — sometimes incomplete, display what's available |
| Sector classification | `yfinance Ticker.info['sector']` — fetched per-ticker, cached |
