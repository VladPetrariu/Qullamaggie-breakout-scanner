"""Tests for the yfinance download helpers in scanner.data (#12)."""

import pandas as pd

from scanner import data


def _frame() -> pd.DataFrame:
    idx = pd.bdate_range(end="2026-07-28", periods=5)
    return pd.DataFrame(
        {"Open": 10.0, "High": 10.5, "Low": 9.5, "Close": 10.0, "Volume": 1e6},
        index=idx,
    )


def test_retry_recovers_tickers_missing_from_first_pass(monkeypatch):
    calls = []

    def fake_download(tickers, period):
        calls.append(list(tickers))
        if len(calls) == 1:
            return {"AAA": _frame()}  # BBB and CCC come back empty
        return {"BBB": _frame(), "CCC": _frame()}

    monkeypatch.setattr(data, "_download_chunk", fake_download)
    result = data._download_chunk_with_retry(["AAA", "BBB", "CCC"], "1y")

    assert set(result) == {"AAA", "BBB", "CCC"}
    # The retry asks only for the tickers that came back empty.
    assert calls == [["AAA", "BBB", "CCC"], ["BBB", "CCC"]]


def test_no_retry_when_first_pass_is_complete(monkeypatch):
    calls = []

    def fake_download(tickers, period):
        calls.append(list(tickers))
        return {t: _frame() for t in tickers}

    monkeypatch.setattr(data, "_download_chunk", fake_download)
    result = data._download_chunk_with_retry(["AAA", "BBB"], "1y")

    assert set(result) == {"AAA", "BBB"}
    assert len(calls) == 1


def test_tickers_missing_after_retry_stay_missing(monkeypatch):
    def fake_download(tickers, period):
        return {"AAA": _frame()} if "AAA" in tickers else {}

    monkeypatch.setattr(data, "_download_chunk", fake_download)
    result = data._download_chunk_with_retry(["AAA", "BBB"], "1y")

    assert set(result) == {"AAA"}
