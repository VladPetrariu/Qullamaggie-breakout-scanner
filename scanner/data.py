"""Download and cache OHLCV market data via yfinance."""

from __future__ import annotations

import pandas as pd
import yfinance as yf
from tqdm import tqdm

from .cache import Cache
from .config import (
    BENCHMARK_FETCH_RETRIES,
    BENCHMARK_TICKERS,
    CACHE_DIR,
    CACHE_PRICES_TTL_HOURS,
    DOWNLOAD_CHUNK_SIZE,
    PREFLIGHT_BENCHMARKS,
    PRICE_HISTORY_PERIOD,
)


def _set_tz_cache_location() -> None:
    """Point yfinance's timezone cache at a project-local sqlite file.

    The default location is a single sqlite file under the user's cache
    directory, shared by every yfinance process; with ~14 download threads
    it is what the recurring ``OperationalError('unable to open database
    file')`` failures point at (#12). A project-local cache avoids the
    contention. Called once per download run, before any yf.download.
    """
    try:
        yf.set_tz_cache_location(str(CACHE_DIR / "yfinance"))
    except Exception:
        pass  # older yfinance without the API — downloads still work


def download_prices(
    tickers: list[str],
    cache: Cache,
    *,
    period: str = PRICE_HISTORY_PERIOD,
    chunk_size: int = DOWNLOAD_CHUNK_SIZE,
    force: bool = False,
) -> dict[str, pd.DataFrame]:
    """Download daily OHLCV for *tickers* + benchmarks.

    Returns a dict mapping each ticker to a DataFrame with columns
    [Open, High, Low, Close, Volume] and a DatetimeIndex.

    Data is cached as a single parquet file keyed by today's date;
    subsequent calls on the same day return instantly from cache.
    force=True skips the cache read and re-downloads (the preflight
    gate uses this — a poisoned same-day cache can't heal itself).
    """
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    cache_key = f"prices_{today}"
    if period != PRICE_HISTORY_PERIOD:
        cache_key = f"prices_{period}_{today}"

    if not force:
        cached_df = cache.get_df(cache_key, max_age_hours=CACHE_PRICES_TTL_HOURS)
        if cached_df is not None:
            print(f"  Using cached price data ({cache_key})")
            return _long_to_dict(cached_df)

    _set_tz_cache_location()

    # Merge benchmarks into the download list (deduped)
    all_tickers = sorted(set(tickers) | set(BENCHMARK_TICKERS))

    chunks = [
        all_tickers[i : i + chunk_size]
        for i in range(0, len(all_tickers), chunk_size)
    ]

    all_data: dict[str, pd.DataFrame] = {}
    failed_chunks = 0

    for chunk in tqdm(chunks, desc="  Downloading prices", unit="batch"):
        result = _download_chunk_with_retry(chunk, period)
        all_data.update(result)
        if not result:
            failed_chunks += 1

    if failed_chunks:
        print(f"  Warning: {failed_chunks}/{len(chunks)} batches returned no data")

    # Benchmarks ride in their own small download with retries: the live era
    # lost SPY from 17 of 35 daily files when it fell out of throttled
    # 500-ticker batches, silently degrading regime and RS inputs.
    bench = _download_benchmarks(period)
    all_data.update(bench)

    missing = [t for t in all_tickers if t not in all_data]
    if missing:
        print(
            f"  Warning: {len(missing):,} of {len(all_tickers):,} requested "
            f"tickers returned no data ({len(all_data):,} received)"
        )

    if all_data:
        cache.set_df(cache_key, _dict_to_long(all_data))

    return all_data


def _download_benchmarks(period: str) -> dict[str, pd.DataFrame]:
    for attempt in range(1, BENCHMARK_FETCH_RETRIES + 1):
        bench = _download_chunk(sorted(BENCHMARK_TICKERS), period)
        if all(b in bench for b in PREFLIGHT_BENCHMARKS):
            return bench
        if attempt < BENCHMARK_FETCH_RETRIES:
            print(f"  Benchmark download incomplete — retrying ({attempt}/{BENCHMARK_FETCH_RETRIES})")
    print("  Warning: benchmark download incomplete after retries")
    return bench


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_KEEP_COLS = ["Open", "High", "Low", "Close", "Volume"]


def _download_chunk_with_retry(
    tickers: list[str], period: str
) -> dict[str, pd.DataFrame]:
    """Download one chunk, retrying the tickers that came back empty once.

    Per-ticker failures inside a batch (throttling, tz-cache contention)
    are usually transient, and the missing names include mega-caps — on
    2026-10-28 about 36% of the universe came back empty (#12). One retry
    of just the missing tickers recovers most of them without re-running
    the whole 500-ticker batch.
    """
    result = _download_chunk(tickers, period)
    missing = [t for t in tickers if t not in result]
    if missing:
        result.update(_download_chunk(missing, period))
    return result


def _download_chunk(tickers: list[str], period: str) -> dict[str, pd.DataFrame]:
    """Download one batch of tickers via yf.download."""
    try:
        raw = yf.download(
            tickers,
            period=period,
            progress=False,
            auto_adjust=True,
            ignore_tz=True,
        )
    except Exception as exc:
        print(f"    Batch error ({len(tickers)} tickers): {exc}")
        return {}

    if raw.empty:
        return {}

    result: dict[str, pd.DataFrame] = {}

    # Single ticker → flat columns, no MultiIndex
    if len(tickers) == 1:
        df = _normalise_columns(raw)
        if df is not None:
            result[tickers[0]] = df
        return result

    # Multi-ticker → MultiIndex columns
    if not isinstance(raw.columns, pd.MultiIndex):
        return result

    # Detect column layout: (Price, Ticker) or (Ticker, Price)
    level0 = set(raw.columns.get_level_values(0).unique())
    price_at_level0 = bool(level0 & {"Close", "Open", "High", "Low", "Volume"})

    for ticker in tickers:
        try:
            if price_at_level0:
                # Default layout: (Price, Ticker)
                ticker_df = raw.xs(ticker, level=1, axis=1)
            else:
                # group_by='ticker' layout: (Ticker, Price)
                ticker_df = raw[ticker]

            df = _normalise_columns(ticker_df)
            if df is not None:
                result[ticker] = df
        except (KeyError, TypeError):
            continue

    return result


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame | None:
    """Ensure standard column names and drop rows missing Close."""
    # yfinance sometimes returns lowercase columns
    df = df.copy()
    df.columns = [c.title() if isinstance(c, str) else c for c in df.columns]

    missing = [c for c in _KEEP_COLS if c not in df.columns]
    if "Close" not in df.columns:
        return None
    if missing:
        for col in missing:
            df[col] = float("nan")

    df = df[_KEEP_COLS]
    df = df.dropna(subset=["Close"])
    if df.empty:
        return None
    return df


# ---------------------------------------------------------------------------
# Long ↔ dict conversions for parquet caching
# ---------------------------------------------------------------------------


def _dict_to_long(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Convert {ticker: df} → single long-format DataFrame."""
    frames = []
    for ticker, df in data.items():
        chunk = df.copy()
        chunk["Ticker"] = ticker
        frames.append(chunk)
    combined = pd.concat(frames)
    combined.index.name = "Date"
    return combined


def _long_to_dict(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Convert long-format DataFrame → {ticker: df}."""
    result: dict[str, pd.DataFrame] = {}
    for ticker, group in df.groupby("Ticker"):
        clean = group.drop(columns=["Ticker"]).sort_index()
        result[ticker] = clean
    return result
