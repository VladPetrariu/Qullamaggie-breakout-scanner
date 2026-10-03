import pandas as pd

from scanner.signals import generate_signals


def _fake_price_df(rows: int = 20) -> pd.DataFrame:
    """Enough rows to clear the ATR_PERIOD + 1 check."""
    return pd.DataFrame({
        "Open": [10.0] * rows,
        "High": [10.5] * rows,
        "Low": [9.5] * rows,
        "Close": [10.0] * rows,
        "Volume": [100_000] * rows,
    })


def test_non_equity_quote_type_is_skipped():
    """A fund/ETF that reached the top 50 and got a quote_type is skipped,
    even though it has no level_value (so it can't fall through to a later
    skip reason for the wrong cause)."""
    watchlist = [{
        "ticker": "WEAT",
        "quote_type": "ETF",
    }]
    price_data = {"WEAT": _fake_price_df()}

    signals, summary = generate_signals(
        watchlist, regime="favorable", price_data=price_data,
    )

    assert signals == []
    assert summary["skip_reasons"]["not_equity"] == 1
    assert summary["skip_reasons"]["no_level"] == 0


def test_equity_quote_type_is_not_skipped_for_that_reason():
    """A real stock's quote_type never trips the not_equity skip. It still
    gets skipped for a different reason (no level_value here), proving the
    not_equity check ran and passed rather than being bypassed."""
    watchlist = [{
        "ticker": "AAPL",
        "quote_type": "EQUITY",
    }]
    price_data = {"AAPL": _fake_price_df()}

    signals, summary = generate_signals(
        watchlist, regime="favorable", price_data=price_data,
    )

    assert summary["skip_reasons"]["not_equity"] == 0
    assert summary["skip_reasons"]["no_level"] == 1


def test_missing_quote_type_is_not_skipped_as_non_equity():
    """A stock never profiled (outside the top 50) has no quote_type at all.
    That must not be treated as non-equity — the check is a backstop only
    for stocks it actually got data on."""
    watchlist = [{
        "ticker": "MSFT",
    }]
    price_data = {"MSFT": _fake_price_df()}

    signals, summary = generate_signals(
        watchlist, regime="favorable", price_data=price_data,
    )

    assert summary["skip_reasons"]["not_equity"] == 0