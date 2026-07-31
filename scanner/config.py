"""All constants, thresholds, and mappings for the scanner."""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (relative to project root)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "cache"
SCANS_DIR = PROJECT_ROOT / "scans"

# ---------------------------------------------------------------------------
# Universe filters
# ---------------------------------------------------------------------------
MIN_PRICE = 5.0
MIN_AVG_VOLUME = 500_000
VOLUME_AVG_PERIOD = 20  # days used for avg-volume filter

# ---------------------------------------------------------------------------
# Data download
# ---------------------------------------------------------------------------
PRICE_HISTORY_PERIOD = "1y"  # yfinance period string
DOWNLOAD_CHUNK_SIZE = 500    # tickers per yfinance batch call
CACHE_PRICES_TTL_HOURS = 16  # price cache valid for this many hours
CACHE_UNIVERSE_TTL_HOURS = 7 * 24  # ticker list cache valid 7 days

# ---------------------------------------------------------------------------
# Technical indicator periods
# ---------------------------------------------------------------------------
EMA_PERIODS = (10, 20, 50)
ATR_PERIOD = 14
RS_LOOKBACK = 20       # days for relative-strength computation
ABR_PERIOD = 21        # average body range lookback

# ---------------------------------------------------------------------------
# Market context thresholds
# Each indicator maps regime names to boundary values.
# "favorable" means >= that value is favorable, etc.
# ---------------------------------------------------------------------------
MARKET_CONTEXT_THRESHOLDS = {
    "pct_above_50ma": {"favorable": 60, "mixed": 45, "caution": 30},
    "pct_above_20ma": {"favorable": 55, "mixed": 40, "caution": 25},
    "highs_lows_ratio": {"favorable": 2.0, "mixed": 1.0, "caution": 0.5},
    "vix_level": {"favorable": 18, "caution": 25, "risk_off": 32},
}

# ---------------------------------------------------------------------------
# Catalyst detection
# ---------------------------------------------------------------------------
EARNINGS_LOOKBACK_DAYS = 30
VOLUME_SPIKE_THRESHOLD = 3.0  # multiple of 20-day avg volume

CATALYST_HALFLIFE = {
    "tier1": 4,   # war / shock events
    "tier2": 10,  # IPO / policy
    "tier3": 18,  # gradual / thematic
}

# Freshness score weights (from flowchart)
FRESHNESS_AGE_WEIGHT = 0.40
FRESHNESS_EXT_WEIGHT = 0.60

# ---------------------------------------------------------------------------
# Consolidation (Section A)
# ---------------------------------------------------------------------------
CONSOLIDATION_MIN_DAYS = 3
CONSOLIDATION_MAX_DAYS = 90
CANDLE_QUALITY_IDEAL = 0.52   # body/range ratio (top ~10%)
CANDLE_QUALITY_OK = 0.44      # above median
CANDLE_QUALITY_BARCODE = 0.38 # bottom ~10%

# ---------------------------------------------------------------------------
# Breakout level lookbacks (Section D)
# ---------------------------------------------------------------------------
MULTI_YEAR_LOOKBACK_DAYS = 5 * 252  # ~5 years of trading days

# ---------------------------------------------------------------------------
# SPDR Sector ETF mapping
# ---------------------------------------------------------------------------
SECTOR_ETFS = {
    # Keys match yfinance Ticker.info['sector'] values
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financial Services": "XLF",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

# Extra tickers that always need price data (benchmarks)
BENCHMARK_TICKERS = ["SPY", "^VIX"] + list(SECTOR_ETFS.values())

# ---------------------------------------------------------------------------
# Data preflight gate (step 2.5 — 2026-07-29 counterfactual analysis)
# The live era ran 6 of 35 scan days on catastrophically stale prices and
# lost SPY from 17 of 35 downloads; the date-keyed cache meant shell-level
# retries re-read the same bad file. The gate re-downloads (bypassing the
# cache) and refuses to emit signals if the prior session is still missing.
# Clean days show 93.6-98.9% coverage, so 90 separates clean from broken;
# 95 misfires on normal days.
# ---------------------------------------------------------------------------
PREFLIGHT_BENCHMARKS = ("SPY", "^VIX")   # must carry the prior session's bar
PREFLIGHT_MIN_COVERAGE_PCT = 90.0        # of downloaded universe with that bar
PREFLIGHT_MIN_UNIVERSE_FRACTION = 0.5    # downloaded stock tickers / requested — catches
                                         # throttling that drops whole 500-ticker chunks
                                         # (clean days deliver ~65-77% of the EDGAR list;
                                         # the catastrophic live days were under 43%)
PREFLIGHT_MAX_ATTEMPTS = 3               # total tries (1 initial + 2 re-downloads)
PREFLIGHT_RETRY_WAIT_S = 300             # pause between re-downloads
BENCHMARK_FETCH_RETRIES = 3              # dedicated small benchmark download

# ---------------------------------------------------------------------------
# Trade signal generation (Phase 10, step 51; revised 2026-07-29)
# Exit policy from the 2026-07-29 exit-variant re-test on 13,456 multi-window
# picks (test_results/2026-07-29_counterfactual_analysis.md): keep the 3×ATR
# stop and 10d hold, sell half at +3×ATR, trail the remainder at 3×ATR
# ("partial3_trail3") — favorable-regime winsorized expectancy +0.135% →
# +0.441%/trade, and it flips the top-5 rank bucket from -0.234% to +0.329%.
# Regime policy: corrected-regime analysis showed caution/risk_off days carry
# negative expectancy (the robust component, day-clustered z≈2.2-2.9), while
# a strict favorable-only gate trades too rarely (~6 days/mo) to ever reach
# the go-live gate — so mixed trades at half risk instead of not at all.
# ---------------------------------------------------------------------------
DEFAULT_ACCOUNT_EQUITY = 25_000.0   # paper account starting balance; --equity overrides
RISK_PER_TRADE_PCT = 0.01           # of account at risk per trade, × regime multiplier
MAX_POSITION_PCT = 0.20             # cap any single position at 20% of account
MAX_SIGNALS_PER_DAY = 5             # signals issued per scan (top-5 outperforms deeper ranks)
MAX_OPEN_POSITIONS = 8              # simulator slot cap (slot experiment: 8 > 5; cash binds >10)
STOP_ATR_MULTIPLIER = 3.0           # entry minus N × ATR(14) = stop
PARTIAL_PROFIT_ATR = 3.0            # resting limit sells 50% at entry + N × ATR
TRAIL_STOP_ATR = 3.0                # after the partial: stop = highest close − N × ATR
MAX_HOLD_DAYS = 10                  # time-based exit horizon (15/20d tested worse)
MIN_STOP_DISTANCE_PCT = 3.0         # floor: don't place a stop tighter than this
MAX_ENTRY_OVERSHOOT_PCT = 0.5       # skip if last_close > entry × (1 + this/100) — too extended
MAX_LEVEL_DISTANCE_PCT = 3.0        # skip if level is more than this % above last_close — too far to trigger
ENTRY_BUFFER_PCT = 0.1              # limit-order placed at entry × (1 + this/100)
MAX_ADR20_PCT = 8.0                 # skip lottery-ticket setups: ADR20 > 8% bucket wins 41.5%, median −4.9%
SIGNAL_TRADABLE_REGIMES = ("favorable", "mixed")
REGIME_RISK_MULTIPLIERS = {"favorable": 1.0, "mixed": 0.5}

# ---------------------------------------------------------------------------
# Paper-trading simulator (Phase 10, step 52 — Option A)
# Local fill simulation against real daily OHLC. State in paper_trades/
# (gitignored — personal trading results stay off GitHub).
# ---------------------------------------------------------------------------
PAPER_DIR = PROJECT_ROOT / "paper_trades"
PAPER_STALE_DATA_FORCE_CLOSE_DAYS = 5  # force-close after N straight days without data
PAPER_SPLIT_TOLERANCE_PCT = 2.0        # rescale prices when adjusted history shifts more than this
