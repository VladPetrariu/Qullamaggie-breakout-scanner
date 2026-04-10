"""Download and cache OHLCV market data via yfinance."""

from __future__ import annotations

import pandas as pd
import yfinance as yf
from tqdm import tqdm

from .cache import Cache
from .config import (
    BENCHMARK_TICKERS,
    CACHE_PRICES_TTL_HOURS,
    DOWNLOAD_CHUNK_SIZE,
    PRICE_HISTORY_PERIOD,
)


def download_prices(
    tickers: list[str],
    cache: Cache,
    *,
    period: str = PRICE_HISTORY_PERIOD,
    chunk_size: int = DOWNLOAD_CHUNK_SIZE,
) -> dict[str, pd.DataFrame]:
    """Download daily OHLCV for *tickers* + benchmarks.

    Returns a dict mapping each ticker to a DataFrame with columns
    [Open, High, Low, Close, Volume] and a DatetimeIndex.

    Data is cached as a single parquet file keyed by today's date;
    subsequent calls on the same day return instantly from cache.
    """
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    cache_key = f"prices_{today}"

    cached_df = cache.get_df(cache_key, max_age_hours=CACHE_PRICES_TTL_HOURS)
    if cached_df is not None:
        print(f"  Using cached price data ({cache_key})")
        return _long_to_dict(cached_df)

    # Merge benchmarks into the download list (deduped)
    all_tickers = sorted(set(tickers) | set(BENCHMARK_TICKERS))

    chunks = [
        all_tickers[i : i + chunk_size]
        for i in range(0, len(all_tickers), chunk_size)
    ]

    all_data: dict[str, pd.DataFrame] = {}
    failed_chunks = 0

    for chunk in tqdm(chunks, desc="  Downloading prices", unit="batch"):
        result = _download_chunk(chunk, period)
        all_data.update(result)
        if not result:
            failed_chunks += 1

    if failed_chunks:
        print(f"  Warning: {failed_chunks}/{len(chunks)} batches returned no data")

    if all_data:
        cache.set_df(cache_key, _dict_to_long(all_data))

    return all_data


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_KEEP_COLS = ["Open", "High", "Low", "Close", "Volume"]


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
