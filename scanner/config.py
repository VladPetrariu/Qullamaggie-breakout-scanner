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
# Trade signal generation (Phase 10, step 51)
# Picked from exit-strategy backtest (test_results/2026-05-01_exit_strategies.md):
# 3×ATR stop / 10d max hold / no trailing was the best risk-managed strategy.
# Mixed/caution regimes had negative expectancy across every exit policy,
# so we trade only in favorable regime.
# ---------------------------------------------------------------------------
DEFAULT_ACCOUNT_EQUITY = 25_000.0   # paper account starting balance; --equity overrides
RISK_PER_TRADE_PCT = 0.01           # 1% of account at risk per trade
MAX_POSITION_PCT = 0.20             # cap any single position at 20% of account
MAX_CONCURRENT_POSITIONS = 5        # max signals issued per day in favorable regime
STOP_ATR_MULTIPLIER = 3.0           # entry minus N × ATR(14) = stop
MAX_HOLD_DAYS = 10                  # time-based exit horizon
MIN_STOP_DISTANCE_PCT = 3.0         # floor: don't place a stop tighter than this
MAX_ENTRY_OVERSHOOT_PCT = 0.5       # skip if last_close > entry × (1 + this/100) — too extended
MAX_LEVEL_DISTANCE_PCT = 3.0        # skip if level is more than this % above last_close — too far to trigger
ENTRY_BUFFER_PCT = 0.1              # limit-order placed at entry × (1 + this/100)
SIGNAL_TRADABLE_REGIMES = ("favorable",)
