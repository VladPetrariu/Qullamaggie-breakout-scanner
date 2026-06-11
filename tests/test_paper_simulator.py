"""Unit and end-to-end tests for the paper-trading simulator (step 52).

Run from the project root: .venv/bin/python -m pytest tests/
"""

import json
from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from scanner.paper_simulator import (
    _attempt_fill,
    _basis_factor,
    _check_exit,
    _earliest_active_date,
    _max_drawdown_pct,
    _rescale_order,
    _rescale_position,
    _size_position,
    run_paper_simulator,
)

ET_TZ = ZoneInfo("America/New_York")
PT_TZ = ZoneInfo("America/Vancouver")


# ── Helpers ──────────────────────────────────────────────────────────────


def _df(rows):
    """rows: list of (date_str, open, high, low, close)."""
    idx = pd.to_datetime([r[0] for r in rows])
    return pd.DataFrame(
        {
            "Open": [r[1] for r in rows],
            "High": [r[2] for r in rows],
            "Low": [r[3] for r in rows],
            "Close": [r[4] for r in rows],
            "Volume": [1_000_000] * len(rows),
        },
        index=idx,
    )


def _bar(open_, high, low, close):
    return pd.Series({"Open": open_, "High": high, "Low": low, "Close": close})


def _order(ticker="TST", limit=10.0, stop=9.0, last_close=9.9, rank=1):
    return {
        "ticker": ticker,
        "rank": rank,
        "level_type": "ath",
        "signal_date": "2026-05-02",
        "activation_date": "2026-05-02",
        "limit_entry": limit,
        "stop_price": stop,
        "signal_last_close": last_close,
        "max_hold_days": 10,
    }


def _position(fill=10.0, stop=9.0, shares=100, days_held=0, max_hold=10):
    return {
        "ticker": "TST",
        "rank": 1,
        "level_type": "ath",
        "signal_date": "2026-05-02",
        "fill_date": "2026-05-04",
        "fill_price": fill,
        "shares": shares,
        "stop_price": stop,
        "max_hold_days": max_hold,
        "days_held": days_held,
        "risk_dollars": 250.0,
        "mae_pct": 0.0,
        "mfe_pct": 0.0,
        "last_mark_close": fill,
        "last_mark_date": "2026-05-04",
        "missing_days": 0,
    }


# ── Fill rules ───────────────────────────────────────────────────────────


def test_fill_at_limit_when_high_crosses():
    price, status = _attempt_fill(_order(limit=10.0), _bar(9.9, 10.05, 9.85, 10.02))
    assert status == "filled"
    assert price == 10.0


def test_no_fill_when_high_below_limit():
    price, status = _attempt_fill(_order(limit=10.0), _bar(9.5, 9.95, 9.4, 9.9))
    assert price is None
    assert status == "not_triggered"


def test_small_gap_fills_at_open():
    # Open above limit but within the 0.5% chase tolerance → fill at open.
    price, status = _attempt_fill(_order(limit=10.0), _bar(10.03, 10.2, 10.0, 10.1))
    assert status == "filled"
    assert price == 10.03


def test_big_gap_abandons_order():
    # Open more than 0.5% above limit → don't chase.
    price, status = _attempt_fill(_order(limit=10.0), _bar(10.5, 10.8, 10.4, 10.6))
    assert price is None
    assert status == "gapped_past_entry"


def test_open_exactly_at_limit_fills_at_open():
    price, status = _attempt_fill(_order(limit=10.0), _bar(10.0, 10.3, 9.9, 10.2))
    assert status == "filled"
    assert price == 10.0


# ── Position sizing ──────────────────────────────────────────────────────


def test_sizing_risk_based():
    # $25k equity, 1% risk = $250, $1 stop distance → 250 shares.
    shares, risk = _size_position(25_000, 25_000, 10.0, 9.0)
    assert shares == 250
    assert risk == 250.0


def test_sizing_capped_at_20_pct():
    # Tight stop would suggest 2500 shares ($25k) — cap at 20% = $5k = 500 shares.
    shares, _ = _size_position(25_000, 25_000, 10.0, 9.9)
    assert shares == 500


def test_sizing_capped_by_cash():
    shares, _ = _size_position(25_000, 1_000, 10.0, 9.0)
    assert shares == 100


def test_sizing_zero_when_stop_above_fill():
    shares, _ = _size_position(25_000, 25_000, 10.0, 10.5)
    assert shares == 0


# ── Exit rules ───────────────────────────────────────────────────────────


def test_stop_exit_at_stop_price():
    exit_ = _check_exit(_position(stop=9.0), _bar(9.5, 9.6, 8.9, 9.2))
    assert exit_ == (9.0, "stop")


def test_gap_through_stop_exits_at_open():
    exit_ = _check_exit(_position(stop=9.0), _bar(8.5, 8.8, 8.3, 8.6))
    assert exit_ == (8.5, "stop_gap")


def test_time_exit_at_close_on_final_day():
    exit_ = _check_exit(_position(days_held=9, max_hold=10), _bar(10.5, 10.8, 10.4, 10.7))
    assert exit_ == (10.7, "time")


def test_stop_beats_time_exit_on_same_bar():
    exit_ = _check_exit(_position(stop=9.0, days_held=9, max_hold=10), _bar(9.5, 9.6, 8.9, 9.2))
    assert exit_ == (9.0, "stop")


def test_no_exit_mid_hold():
    exit_ = _check_exit(_position(days_held=3), _bar(10.5, 10.8, 10.4, 10.7))
    assert exit_ is None


# ── Activation timing (cutoff is 9:30 US/Eastern, not machine-local) ────


def test_premarket_scan_trades_same_day():
    assert _earliest_active_date(
        date(2026, 5, 4), "2026-05-04T08:00:00", local_tz=ET_TZ
    ) == date(2026, 5, 4)


def test_postopen_scan_trades_next_day():
    assert _earliest_active_date(
        date(2026, 5, 4), "2026-05-04T17:30:00", local_tz=ET_TZ
    ) == date(2026, 5, 5)


def test_pacific_late_morning_is_next_day():
    # 8 AM Vancouver = 11 AM Eastern — market already open; trading the
    # same day would fill against bar hours that predate the signal.
    assert _earliest_active_date(
        date(2026, 5, 4), "2026-05-04T08:00:00", local_tz=PT_TZ
    ) == date(2026, 5, 5)


def test_pacific_early_morning_same_day():
    # 6 AM Vancouver = 9 AM Eastern — still pre-open.
    assert _earliest_active_date(
        date(2026, 5, 4), "2026-05-04T06:00:00", local_tz=PT_TZ
    ) == date(2026, 5, 4)


def test_weekend_scan_keeps_file_date():
    # Saturday 1 AM scan — calendar alignment to Monday happens in the day loop.
    assert _earliest_active_date(
        date(2026, 5, 2), "2026-05-02T01:02:35", local_tz=PT_TZ
    ) == date(2026, 5, 2)


# ── Split/adjustment rescaling ───────────────────────────────────────────


def test_basis_factor_none_within_tolerance():
    assert _basis_factor(100.0, 100.5) is None


def test_basis_factor_detects_split():
    assert _basis_factor(100.0, 50.0) == pytest.approx(0.5)


def test_rescale_order_halves_prices():
    order = _order(limit=101.0, stop=95.0, last_close=100.0)
    _rescale_order(order, 0.5)
    assert order["limit_entry"] == pytest.approx(50.5)
    assert order["stop_price"] == pytest.approx(47.5)


def test_rescale_position_preserves_value():
    pos = _position(fill=100.0, stop=90.0, shares=50)
    value_before = pos["shares"] * pos["last_mark_close"]
    cash = _rescale_position(pos, 0.5)
    assert pos["shares"] == 100
    assert cash == pytest.approx(0.0)
    assert pos["fill_price"] == pytest.approx(50.0)
    assert pos["shares"] * pos["last_mark_close"] + cash == pytest.approx(value_before)


def test_rescale_position_settles_fractional_shares_in_cash():
    # 3:2 split: 33 shares at $90 → 49.5 shares at $60. The half share
    # settles as $30 cash-in-lieu, keeping value exactly invariant.
    pos = _position(fill=90.0, stop=80.0, shares=33)
    value_before = pos["shares"] * pos["last_mark_close"]
    cash = _rescale_position(pos, 2 / 3)
    assert pos["shares"] == 49
    assert cash == pytest.approx(30.0)
    assert pos["shares"] * pos["last_mark_close"] + cash == pytest.approx(value_before)


def test_max_drawdown_seeded_with_starting_equity():
    # An account that only declines must report drawdown from inception.
    curve = [{"equity": 23_750.0}, {"equity": 22_500.0}]
    assert _max_drawdown_pct(curve, 25_000.0) == pytest.approx(-10.0)


# ── End-to-end simulation ────────────────────────────────────────────────

MAY_DAYS = [
    "2026-05-04", "2026-05-05", "2026-05-06", "2026-05-07", "2026-05-08",
    "2026-05-11", "2026-05-12", "2026-05-13", "2026-05-14", "2026-05-15",
    "2026-05-18", "2026-05-19",
]


def _flat(days, price):
    return _df([(d, price, price, price, price) for d in days])


def _write_signals(scans_dir, signals, file_date="2026-05-02"):
    scans_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": {"signals_issued": len(signals)},
        "signals": signals,
    }
    with open(scans_dir / f"signals_{file_date}.json", "w") as f:
        json.dump(payload, f)


def _sig(ticker, rank, limit, stop, last_close):
    return {
        "ticker": ticker,
        "rank": rank,
        "level_type": "ath",
        "last_close": last_close,
        "limit_entry": limit,
        "stop_price": stop,
        "max_hold_days": 10,
        "generated_at": "2026-05-02T01:02:35",
    }


@pytest.fixture
def e2e_dirs(tmp_path):
    return tmp_path / "paper", tmp_path / "scans"


def _e2e_data():
    """Five scenarios on a 12-trading-day May calendar:
    AAA fills at limit then time-exits +10%; BBB never triggers; CCC gaps
    past entry; DDD fills then stops out next day; EEE fills and hits the
    stop the same day."""
    data = {"SPY": _flat(MAY_DAYS, 500.0)}

    aaa = [("2026-05-04", 9.90, 10.05, 9.85, 10.02)]
    rising = [10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 11.0, 11.0]
    for day, px in zip(MAY_DAYS[1:], rising):
        aaa.append((day, px, px + 0.05, px - 0.05, px))
    data["AAA"] = _df(aaa)

    data["BBB"] = _flat(MAY_DAYS, 49.0)  # limit 50 never reached

    ccc = [("2026-05-04", 40.50, 40.80, 40.40, 40.60)]  # gaps past 40 limit
    data["CCC"] = _df(ccc + [(d, 41, 41, 41, 41) for d in MAY_DAYS[1:]])

    ddd = [
        ("2026-05-04", 19.80, 20.30, 19.50, 20.10),  # fills at 20
        ("2026-05-05", 19.00, 19.20, 17.90, 18.00),  # low hits 18 stop
    ]
    data["DDD"] = _df(ddd + [(d, 18, 18, 18, 18) for d in MAY_DAYS[2:]])

    eee = [("2026-05-04", 29.90, 30.40, 29.00, 29.30)]  # fills at 30, low hits 29.4 stop
    data["EEE"] = _df(eee + [(d, 29, 29, 29, 29) for d in MAY_DAYS[1:]])
    return data


def _run(paper_dir, scans_dir, data, today=date(2026, 5, 20)):
    return run_paper_simulator(
        paper_dir=paper_dir,
        scans_dir=scans_dir,
        fetch_prices=lambda tickers, period: {
            t: df for t, df in data.items() if t in tickers
        },
        today=today,
    )


def test_end_to_end_fills_exits_and_accounting(e2e_dirs, capsys):
    paper_dir, scans_dir = e2e_dirs
    _write_signals(scans_dir, [
        _sig("AAA", 1, 10.0, 9.0, 9.90),
        _sig("BBB", 2, 50.0, 47.0, 49.0),
        _sig("CCC", 3, 40.0, 37.0, 39.9),
        _sig("DDD", 4, 20.0, 18.0, 19.8),
        _sig("EEE", 5, 30.0, 29.4, 29.9),
    ])
    state = _run(paper_dir, scans_dir, _e2e_data())

    trades = json.loads((paper_dir / "trades.json").read_text())
    by_ticker = {t["ticker"]: t for t in trades}

    # EEE: same-day stop. Sized after AAA ($2.5k) and DDD ($2.5k) drew cash.
    eee = by_ticker["EEE"]
    assert eee["exit_reason"] == "stop_same_day"
    assert eee["days_held"] == 0
    assert eee["fill_price"] == 30.0
    assert eee["exit_price"] == 29.4
    assert eee["shares"] == 166  # 20% equity cap: 5000 / 30

    # DDD: stopped at the stop price the day after fill.
    ddd = by_ticker["DDD"]
    assert ddd["exit_reason"] == "stop"
    assert ddd["days_held"] == 1
    assert ddd["shares"] == 125  # risk-based: 250 / 2.0
    assert ddd["pnl_dollars"] == pytest.approx(-250.0)

    # AAA: held 10 trading days, time exit at 11.00 close.
    aaa = by_ticker["AAA"]
    assert aaa["exit_reason"] == "time"
    assert aaa["days_held"] == 10
    assert aaa["exit_date"] == "2026-05-18"
    assert aaa["shares"] == 250
    assert aaa["pnl_dollars"] == pytest.approx(250.0)

    # Orders that never became positions.
    history = {o["ticker"]: o["status"] for o in state["order_history"]}
    assert history["BBB"] == "not_triggered"
    assert history["CCC"] == "gapped_past_entry"

    # Equity: 25000 + 250 (AAA) − 250 (DDD) − 99.6 (EEE).
    assert state["open_positions"] == []
    assert state["pending_orders"] == []
    final_equity = state["equity_curve"][-1]["equity"]
    assert final_equity == pytest.approx(24_900.40)
    assert state["cash"] == pytest.approx(24_900.40)


def test_rerun_is_idempotent(e2e_dirs):
    paper_dir, scans_dir = e2e_dirs
    _write_signals(scans_dir, [_sig("AAA", 1, 10.0, 9.0, 9.90)])
    data = {"SPY": _e2e_data()["SPY"], "AAA": _e2e_data()["AAA"]}

    first = _run(paper_dir, scans_dir, data)
    second = _run(paper_dir, scans_dir, data)

    assert len(second["equity_curve"]) == len(first["equity_curve"])
    trades = json.loads((paper_dir / "trades.json").read_text())
    assert len(trades) == 1  # AAA traded once, not twice


def test_slot_limit_blocks_sixth_position(e2e_dirs):
    paper_dir, scans_dir = e2e_dirs
    tickers = ["TK1", "TK2", "TK3", "TK4", "TK5", "TK6"]
    _write_signals(
        scans_dir,
        [_sig(t, i + 1, 10.0, 9.0, 9.9) for i, t in enumerate(tickers)],
    )
    data = {"SPY": _flat(MAY_DAYS, 500.0)}
    for t in tickers:
        # Everything fills at 10 and drifts sideways — no exits.
        data[t] = _df([(d, 9.9, 10.1, 9.8, 10.0) for d in MAY_DAYS])

    # Stop before the 10-day time exit so positions stay open.
    state = _run(paper_dir, scans_dir, data, today=date(2026, 5, 6))

    assert len(state["open_positions"]) == 5
    skipped = [o for o in state["order_history"] if o["status"] == "skipped_no_slot"]
    assert [o["ticker"] for o in skipped] == ["TK6"]  # lowest-ranked loses the slot


def test_split_rescales_order_basis(e2e_dirs):
    paper_dir, scans_dir = e2e_dirs
    # Signal generated at pre-split prices (last_close 100); downloaded
    # history is post-split-adjusted (basis close 50).
    _write_signals(scans_dir, [_sig("SPLT", 1, 101.0, 95.0, 100.0)])
    splt = [("2026-05-01", 49.9, 50.1, 49.8, 50.0),
            ("2026-05-04", 50.2, 50.8, 50.0, 50.6)]
    data = {
        "SPY": _flat(["2026-05-01"] + MAY_DAYS, 500.0),
        "SPLT": _df(splt + [(d, 50.6, 50.7, 50.5, 50.6) for d in MAY_DAYS[1:]]),
    }

    # Stop before the 10-day time exit so the position stays open.
    state = _run(paper_dir, scans_dir, data, today=date(2026, 5, 6))

    assert len(state["open_positions"]) == 1
    pos = state["open_positions"][0]
    assert pos["fill_price"] == pytest.approx(50.5)   # rescaled limit
    assert pos["stop_price"] == pytest.approx(47.5)   # rescaled stop


def test_duplicate_ticker_not_doubled(e2e_dirs):
    paper_dir, scans_dir = e2e_dirs
    # Same ticker signaled on two consecutive days; second order must skip.
    _write_signals(scans_dir, [_sig("AAA", 1, 10.0, 9.0, 9.90)], "2026-05-02")
    sig2 = _sig("AAA", 1, 10.2, 9.2, 10.02)
    sig2["generated_at"] = "2026-05-05T01:00:00"
    _write_signals(scans_dir, [sig2], "2026-05-05")

    data = {"SPY": _e2e_data()["SPY"], "AAA": _e2e_data()["AAA"]}
    state = _run(paper_dir, scans_dir, data)

    held = [o for o in state["order_history"] if o["status"] == "skipped_already_holding"]
    assert len(held) == 1
    assert held[0]["date"] == "2026-05-05"


def test_regenerated_signals_replace_pending_orders(e2e_dirs):
    paper_dir, scans_dir = e2e_dirs
    data = {"SPY": _e2e_data()["SPY"], "AAA": _e2e_data()["AAA"]}
    # First --paper run reads the file before its trade day has simulated.
    _write_signals(scans_dir, [_sig("AAA", 1, 99.0, 90.0, 9.9)])
    _run(paper_dir, scans_dir, data, today=date(2026, 5, 4))
    # Scanner re-run overwrites the file with a corrected limit; the stale
    # 99.0 order must be replaced, not silently kept.
    _write_signals(scans_dir, [_sig("AAA", 1, 10.0, 9.0, 9.9)])
    state = _run(paper_dir, scans_dir, data, today=date(2026, 5, 6))

    filled = [o for o in state["order_history"] if o["status"] == "filled"]
    assert len(filled) == 1
    assert len(state["open_positions"]) == 1
    assert state["open_positions"][0]["fill_price"] == pytest.approx(10.0)


def test_absent_ticker_carries_position(e2e_dirs):
    paper_dir, scans_dir = e2e_dirs
    _write_signals(scans_dir, [_sig("AAA", 1, 10.0, 9.0, 9.90)])
    data = {"SPY": _e2e_data()["SPY"], "AAA": _e2e_data()["AAA"]}
    state = _run(paper_dir, scans_dir, data, today=date(2026, 5, 6))
    assert len(state["open_positions"]) == 1

    # Next run's download fails for AAA entirely (transient yfinance error)
    # — the position must carry untouched, not march toward force-close.
    state = _run(paper_dir, scans_dir, {"SPY": _e2e_data()["SPY"]}, today=date(2026, 5, 9))
    assert len(state["open_positions"]) == 1
    assert state["open_positions"][0]["missing_days"] == 0


def test_newer_signal_supersedes_pending_same_ticker(e2e_dirs):
    paper_dir, scans_dir = e2e_dirs
    # A post-close scan and the next morning's pre-market scan both signal
    # AAA for the same trade day — only the newer order may run.
    sig1 = _sig("AAA", 1, 99.0, 90.0, 9.9)
    sig1["generated_at"] = "2026-05-04T17:30:00"  # post-close → trades May 5
    _write_signals(scans_dir, [sig1], "2026-05-04")
    sig2 = _sig("AAA", 1, 10.12, 9.0, 10.02)
    sig2["generated_at"] = "2026-05-05T01:00:00"  # pre-market → trades May 5
    _write_signals(scans_dir, [sig2], "2026-05-05")

    data = {"SPY": _e2e_data()["SPY"], "AAA": _e2e_data()["AAA"]}
    state = _run(paper_dir, scans_dir, data, today=date(2026, 5, 6))

    superseded = [o for o in state["order_history"] if o["status"] == "superseded"]
    assert len(superseded) == 1
    assert superseded[0]["signal_date"] == "2026-05-04"
    filled = [o for o in state["order_history"] if o["status"] == "filled"]
    assert len(filled) == 1
    assert len(state["open_positions"]) == 1
    assert state["open_positions"][0]["fill_price"] == pytest.approx(10.12)


def test_late_discovered_older_file_does_not_supersede(e2e_dirs):
    paper_dir, scans_dir = e2e_dirs
    data = {"SPY": _e2e_data()["SPY"], "AAA": _e2e_data()["AAA"]}
    # The older file exists but is unreadable on the first run (e.g. a
    # partially-synced scans/ dir) — it gets retried later.
    scans_dir.mkdir(parents=True, exist_ok=True)
    (scans_dir / "signals_2026-05-04.json").write_text("{ truncated")
    sig_new = _sig("AAA", 1, 10.12, 9.0, 10.02)
    sig_new["generated_at"] = "2026-05-05T01:00:00"  # trades May 5
    _write_signals(scans_dir, [sig_new], "2026-05-05")
    _run(paper_dir, scans_dir, data, today=date(2026, 5, 5))

    # The older post-close file becomes readable, with stale levels.
    sig_old = _sig("AAA", 1, 99.0, 90.0, 9.9)
    sig_old["generated_at"] = "2026-05-04T17:30:00"  # also trades May 5
    _write_signals(scans_dir, [sig_old], "2026-05-04")
    state = _run(paper_dir, scans_dir, data, today=date(2026, 5, 6))

    # The fresher order trades; the stale one is superseded — not vice versa.
    filled = [o for o in state["order_history"] if o["status"] == "filled"]
    assert len(filled) == 1
    assert filled[0]["signal_date"] == "2026-05-05"
    superseded = [o for o in state["order_history"] if o["status"] == "superseded"]
    assert [o["signal_date"] for o in superseded] == ["2026-05-04"]
    assert state["open_positions"][0]["fill_price"] == pytest.approx(10.12)


def test_friday_postclose_superseded_by_monday_premarket(e2e_dirs):
    paper_dir, scans_dir = e2e_dirs
    # Friday post-close signal: activation Saturday → first tradable Monday.
    sig_fri = _sig("AAA", 1, 99.0, 90.0, 9.9)
    sig_fri["generated_at"] = "2026-05-01T17:30:00"
    _write_signals(scans_dir, [sig_fri], "2026-05-01")
    # Monday pre-market signal with fresh levels — same first trade day.
    sig_mon = _sig("AAA", 1, 10.0, 9.0, 9.9)
    sig_mon["generated_at"] = "2026-05-04T01:00:00"
    _write_signals(scans_dir, [sig_mon], "2026-05-04")

    data = {"SPY": _e2e_data()["SPY"], "AAA": _e2e_data()["AAA"]}
    state = _run(paper_dir, scans_dir, data, today=date(2026, 5, 5))

    # The calendar collision resolves to the freshest signal.
    superseded = [o for o in state["order_history"] if o["status"] == "superseded"]
    assert [o["signal_date"] for o in superseded] == ["2026-05-01"]
    filled = [o for o in state["order_history"] if o["status"] == "filled"]
    assert len(filled) == 1
    assert filled[0]["signal_date"] == "2026-05-04"
    assert state["open_positions"][0]["fill_price"] == pytest.approx(10.0)
