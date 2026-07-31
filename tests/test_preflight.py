"""Tests for the NYSE calendar and the data-integrity preflight gate."""

from datetime import date

import pandas as pd
import pytest

from scanner.market_calendar import (
    easter_sunday,
    is_trading_day,
    nyse_holidays,
    previous_trading_day,
)
from scanner.preflight import check_price_data
from scanner.signals import _adr20


# ── Calendar ─────────────────────────────────────────────────────────────


def test_easter_known_dates():
    assert easter_sunday(2024) == date(2024, 3, 31)
    assert easter_sunday(2026) == date(2026, 4, 5)


def test_2026_holidays():
    days = nyse_holidays(2026)
    assert date(2026, 1, 1) in days       # New Year's Day (Thursday)
    assert date(2026, 1, 19) in days      # MLK Day
    assert date(2026, 2, 16) in days      # Washington's Birthday
    assert date(2026, 4, 3) in days       # Good Friday
    assert date(2026, 5, 25) in days      # Memorial Day
    assert date(2026, 6, 19) in days      # Juneteenth — the bot traded this day
    assert date(2026, 7, 3) in days       # July 4 observed — this one too
    assert date(2026, 9, 7) in days       # Labor Day
    assert date(2026, 11, 26) in days     # Thanksgiving
    assert date(2026, 12, 25) in days     # Christmas


def test_saturday_new_year_not_observed():
    # Jan 1 2022 fell on Saturday — NYSE did NOT close Friday Dec 31 2021.
    assert date(2021, 12, 31) not in nyse_holidays(2021)
    assert date(2022, 1, 1) not in nyse_holidays(2022)


def test_sunday_holiday_observed_monday():
    # July 4 2021 (Sunday) → observed Monday July 5.
    assert date(2021, 7, 5) in nyse_holidays(2021)


def test_juneteenth_starts_2022():
    assert date(2021, 6, 18) not in nyse_holidays(2021)  # Jun 19 2021 = Saturday


def test_is_trading_day():
    assert is_trading_day(date(2026, 7, 29)) is True    # ordinary Wednesday
    assert is_trading_day(date(2026, 7, 25)) is False   # Saturday
    assert is_trading_day(date(2026, 6, 19)) is False   # Juneteenth
    assert is_trading_day(date(2026, 7, 3)) is False    # July 4 observed


def test_previous_trading_day_skips_holiday_weekend():
    # Monday Jul 6 2026 ← skips the Jul 3 holiday and the weekend → Thu Jul 2.
    assert previous_trading_day(date(2026, 7, 6)) == date(2026, 7, 2)
    assert previous_trading_day(date(2026, 7, 29)) == date(2026, 7, 28)


# ── Preflight gate ───────────────────────────────────────────────────────


def _frame(last_day: str, n: int = 30):
    idx = pd.bdate_range(end=last_day, periods=n)
    return pd.DataFrame(
        {"Open": 10.0, "High": 10.5, "Low": 9.5, "Close": 10.0, "Volume": 1e6},
        index=idx,
    )


def test_preflight_passes_on_fresh_data():
    # Scan on Wed Jul 29 2026; prior session Tue Jul 28.
    data = {"SPY": _frame("2026-07-28"), "^VIX": _frame("2026-07-28")}
    for i in range(20):
        data[f"TK{i}"] = _frame("2026-07-28")
    result = check_price_data(data, date(2026, 7, 29))
    assert result["ok"] is True
    assert result["prior_session"] == "2026-07-28"
    assert result["coverage_pct"] == 100.0


def test_preflight_fails_when_spy_missing():
    data = {"^VIX": _frame("2026-07-28")}
    for i in range(20):
        data[f"TK{i}"] = _frame("2026-07-28")
    result = check_price_data(data, date(2026, 7, 29))
    assert result["ok"] is False
    assert result["missing_benchmarks"] == ["SPY"]


def test_preflight_fails_when_spy_stale():
    # SPY present but its freshest bar is two sessions old.
    data = {"SPY": _frame("2026-07-27"), "^VIX": _frame("2026-07-28")}
    for i in range(20):
        data[f"TK{i}"] = _frame("2026-07-28")
    result = check_price_data(data, date(2026, 7, 29))
    assert result["ok"] is False
    assert result["missing_benchmarks"] == ["SPY"]


def test_preflight_fails_below_coverage_threshold():
    data = {"SPY": _frame("2026-07-28"), "^VIX": _frame("2026-07-28")}
    for i in range(20):  # 15 fresh, 5 stale → 75% < 90%
        data[f"TK{i}"] = _frame("2026-07-28" if i < 15 else "2026-07-24")
    result = check_price_data(data, date(2026, 7, 29))
    assert result["ok"] is False
    assert result["coverage_pct"] == 75.0


def test_preflight_uses_prior_session_not_calendar_day():
    # Scan on Monday: Friday's bar is the freshness requirement.
    data = {"SPY": _frame("2026-07-24"), "^VIX": _frame("2026-07-24")}
    for i in range(20):
        data[f"TK{i}"] = _frame("2026-07-24")
    result = check_price_data(data, date(2026, 7, 27))
    assert result["ok"] is True
    assert result["prior_session"] == "2026-07-24"


def test_preflight_fails_when_download_missing_half_the_universe():
    # Throttling that drops whole 500-ticker chunks shrinks the freshness
    # denominator — the completeness check against the REQUESTED universe
    # must catch it even at 100% freshness among survivors.
    data = {"SPY": _frame("2026-07-28"), "^VIX": _frame("2026-07-28")}
    for i in range(4):
        data[f"TK{i}"] = _frame("2026-07-28")
    requested = [f"TK{i}" for i in range(20)]
    result = check_price_data(data, date(2026, 7, 29), universe=requested)
    assert result["coverage_pct"] == 100.0   # freshness alone would pass
    assert result["universe_fraction"] == pytest.approx(0.2)
    assert result["ok"] is False


def test_preflight_completeness_passes_at_reasonable_fraction():
    data = {"SPY": _frame("2026-07-28"), "^VIX": _frame("2026-07-28")}
    for i in range(14):
        data[f"TK{i}"] = _frame("2026-07-28")
    requested = [f"TK{i}" for i in range(20)]
    result = check_price_data(data, date(2026, 7, 29), universe=requested)
    assert result["ok"] is True
    assert result["universe_fraction"] == pytest.approx(0.7)


def test_preflight_unscheduled_closure_falls_back_one_session():
    # Prior session per the rule-based calendar is Tue Jul 28, but NOBODY —
    # benchmarks included — has a Jul 28 bar while everyone has Jul 27:
    # that pattern is an unscheduled closure, not a bad download.
    data = {"SPY": _frame("2026-07-27"), "^VIX": _frame("2026-07-27")}
    for i in range(20):
        data[f"TK{i}"] = _frame("2026-07-27")
    result = check_price_data(data, date(2026, 7, 29))
    assert result["ok"] is True
    assert result["prior_session"] == "2026-07-27"
    assert "unscheduled" in result["note"]


def test_preflight_partial_staleness_is_not_a_closure():
    # A genuinely bad download shows PARTIAL coverage of the prior session —
    # the closure fallback must not rescue it.
    data = {"SPY": _frame("2026-07-27"), "^VIX": _frame("2026-07-27")}
    for i in range(20):
        data[f"TK{i}"] = _frame("2026-07-28" if i < 5 else "2026-07-27")
    result = check_price_data(data, date(2026, 7, 29))
    assert result["ok"] is False
    assert result["prior_session"] == "2026-07-28"


def test_preflight_benchmarks_excluded_from_coverage():
    # Sector ETF staleness must not sink the universe coverage number.
    data = {"SPY": _frame("2026-07-28"), "^VIX": _frame("2026-07-28"),
            "XLK": _frame("2026-07-20")}
    for i in range(20):
        data[f"TK{i}"] = _frame("2026-07-28")
    result = check_price_data(data, date(2026, 7, 29))
    assert result["ok"] is True
    assert result["n_tickers"] == 20


# ── ADR ceiling helper ───────────────────────────────────────────────────


def test_adr20_computation():
    idx = pd.bdate_range(end="2026-07-28", periods=25)
    # High/Low = 1.05 every day → ADR20 = 5%.
    df = pd.DataFrame(
        {"Open": 100.0, "High": 105.0, "Low": 100.0, "Close": 102.0, "Volume": 1e6},
        index=idx,
    )
    assert _adr20(df) == pytest.approx(5.0)


def test_adr20_needs_20_bars():
    idx = pd.bdate_range(end="2026-07-28", periods=10)
    df = pd.DataFrame(
        {"Open": 100.0, "High": 105.0, "Low": 100.0, "Close": 102.0, "Volume": 1e6},
        index=idx,
    )
    assert _adr20(df) is None
