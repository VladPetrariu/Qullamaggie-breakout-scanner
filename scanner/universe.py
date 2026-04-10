"""Fetch and filter the US stock universe (NYSE + NASDAQ common stocks)."""

import json
import re
import urllib.request
import urllib.error

from .cache import Cache
from .config import (
    CACHE_UNIVERSE_TTL_HOURS,
    MIN_AVG_VOLUME,
    MIN_PRICE,
    VOLUME_AVG_PERIOD,
)

# SEC EDGAR provides all SEC-registered companies with exchange info.
_SEC_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
_TARGET_EXCHANGES = {"NYSE", "Nasdaq"}


def fetch_ticker_list(cache: Cache) -> list[str]:
    """Return sorted list of NYSE/NASDAQ common-stock tickers.

    Uses SEC EDGAR's company_tickers_exchange.json which includes
    exchange information. Results cached for 7 days.
    """
    cached = cache.get_json("ticker_list", max_age_hours=CACHE_UNIVERSE_TTL_HOURS)
    if cached is not None:
        return cached

    tickers = _fetch_sec_tickers()

    result = sorted(tickers)
    if not result:
        raise RuntimeError(
            "Failed to fetch any tickers. Check your internet connection."
        )

    cache.set_json("ticker_list", result)
    return result


def fetch_ticker_info(cache: Cache) -> dict[str, str]:
    """Return {ticker: company_name} for all NYSE/NASDAQ stocks.

    Uses the same SEC EDGAR data as fetch_ticker_list. Cached separately
    so the ticker list can be a simple JSON array.
    """
    cached = cache.get_json(
        "ticker_names", max_age_hours=CACHE_UNIVERSE_TTL_HOURS
    )
    if cached is not None:
        return cached

    info = _fetch_sec_ticker_names()
    if info:
        cache.set_json("ticker_names", info)
    return info


def filter_universe(tickers, price_data):
    """Keep only tickers where last close >= MIN_PRICE and
    20-day average volume >= MIN_AVG_VOLUME.

    Parameters
    ----------
    tickers : list[str]
    price_data : dict[str, DataFrame]  — keyed by ticker, each DF has
        columns including 'Close' and 'Volume' with a DatetimeIndex.

    Returns
    -------
    list[str] — tickers that pass filters, sorted alphabetically.
    """
    passed = []
    for ticker in tickers:
        df = price_data.get(ticker)
        if df is None or len(df) < VOLUME_AVG_PERIOD:
            continue
        recent = df.tail(VOLUME_AVG_PERIOD)
        avg_vol = recent["Volume"].mean()
        last_close = df["Close"].iloc[-1]
        if last_close >= MIN_PRICE and avg_vol >= MIN_AVG_VOLUME:
            passed.append(ticker)
    return sorted(passed)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


def _is_common_stock_ticker(symbol: str) -> bool:
    """Heuristic: common stocks have 1-5 uppercase-letter tickers."""
    return bool(_TICKER_RE.match(symbol))


def _download_sec_data() -> list[list]:
    """Download SEC EDGAR company tickers with exchange info.

    Returns list of [cik, name, ticker, exchange] rows.
    """
    req = urllib.request.Request(
        _SEC_URL,
        headers={
            "User-Agent": "qullamaggie-scanner vlad@example.com",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
            return payload.get("data", [])
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"  Warning: could not fetch SEC data: {exc}")
        return []


def _fetch_sec_tickers() -> set[str]:
    """Return set of common-stock tickers on NYSE/NASDAQ from SEC EDGAR."""
    rows = _download_sec_data()
    tickers: set[str] = set()
    for row in rows:
        if len(row) < 4:
            continue
        ticker = row[2]
        exchange = row[3]
        if exchange not in _TARGET_EXCHANGES:
            continue
        if isinstance(ticker, str) and _is_common_stock_ticker(ticker):
            tickers.add(ticker)
    return tickers


def _fetch_sec_ticker_names() -> dict[str, str]:
    """Return {ticker: company_name} for NYSE/NASDAQ stocks."""
    rows = _download_sec_data()
    names: dict[str, str] = {}
    for row in rows:
        if len(row) < 4:
            continue
        ticker = row[2]
        name = row[1]
        exchange = row[3]
        if exchange not in _TARGET_EXCHANGES:
            continue
        if isinstance(ticker, str) and _is_common_stock_ticker(ticker):
            names[ticker] = name
    return names
