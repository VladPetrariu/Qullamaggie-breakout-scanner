"""Tests for the paper-report statistics (pure functions only)."""

import pytest

from scanner.paper_report import (
    _daily_rows,
    _funnel,
    _gate_status,
    _sparkline,
    _trade_stats,
)


def _trade(pnl_dollars, pnl_pct, days=5, reason="time", mae=-2.0, mfe=4.0, ticker="TST"):
    return {
        "ticker": ticker,
        "pnl_dollars": pnl_dollars,
        "pnl_pct": pnl_pct,
        "days_held": days,
        "exit_reason": reason,
        "mae_pct": mae,
        "mfe_pct": mfe,
    }


def test_trade_stats_empty():
    assert _trade_stats([]) == {"n": 0}


def test_trade_stats_basic():
    trades = [
        _trade(+500.0, +57.9, days=10, ticker="WOLF"),
        _trade(+97.0, +5.2, days=10, ticker="EXTR"),
        _trade(-250.0, -12.5, days=2, reason="stop", ticker="CC"),
    ]
    s = _trade_stats(trades)
    assert s["n"] == 3
    assert s["wins"] == 2 and s["losses"] == 1
    assert s["win_rate"] == pytest.approx(66.667, abs=0.01)
    assert s["realized_pnl"] == pytest.approx(347.0)
    assert s["profit_factor"] == pytest.approx(597.0 / 250.0)
    assert s["expectancy"] == pytest.approx(347.0 / 3)
    assert s["best"] == ("WOLF", 57.9)
    assert s["worst"] == ("CC", -12.5)
    assert s["exit_reasons"] == {"time": 2, "stop": 1}


def test_trade_stats_no_losses_profit_factor_none():
    s = _trade_stats([_trade(+100.0, +5.0)])
    assert s["profit_factor"] is None


def test_funnel_counts():
    history = [
        {"status": "filled"}, {"status": "filled"},
        {"status": "not_triggered"},
        {"status": "gapped_past_entry"},
        {"status": "skipped_no_slot"}, {"status": "skipped_already_holding"},
        {"status": "stale"}, {"status": "superseded"}, {"status": "no_data"},
    ]
    f = _funnel(history, pending=[{"ticker": "X"}])
    assert f["loaded"] == 10
    assert f["filled"] == 2
    assert f["not_triggered"] == 1
    assert f["gapped_past_entry"] == 1
    assert f["skipped"] == 2
    assert f["superseded"] == 1
    assert f["stale"] == 1
    assert f["no_data"] == 1
    assert f["other"] == 0
    assert f["pending"] == 1
    # Fill rate counts only orders that reached a fill decision.
    assert f["attempted"] == 4


def test_gate_status_small_sample():
    s = _trade_stats([_trade(+100.0, +5.0)])
    rows = _gate_status(s, total_return_pct=1.39, max_dd_pct=-1.14)
    by_label = {r[0]: r for r in rows}
    assert by_label["100+ closed trades"][1] is False
    assert by_label["positive total P&L"][1] is True
    # Win rate unjudgeable below 30 trades.
    win_row = [r for r in rows if "win rate" in r[0]][0]
    assert win_row[1] is None
    assert by_label["max drawdown < 10%"][1] is True


def test_gate_status_judges_win_rate_at_30_trades():
    trades = [_trade(+10.0, +1.0)] * 16 + [_trade(-10.0, -1.0)] * 14  # 53.3%
    rows = _gate_status(_trade_stats(trades), 1.0, -2.0)
    win_row = [r for r in rows if "win rate" in r[0]][0]
    assert win_row[1] is True


def test_gate_status_flags_bad_win_rate():
    trades = [_trade(+10.0, +1.0)] * 10 + [_trade(-10.0, -1.0)] * 20  # 33.3%
    rows = _gate_status(_trade_stats(trades), -5.0, -12.0)
    by_label = {r[0]: r for r in rows}
    win_row = [r for r in rows if "win rate" in r[0]][0]
    assert win_row[1] is False
    assert by_label["positive total P&L"][1] is False
    assert by_label["max drawdown < 10%"][1] is False


def test_daily_rows_pnl_chain():
    curve = [
        {"date": "2026-05-04", "equity": 25_100.0, "open_positions": 3},
        {"date": "2026-05-05", "equity": 24_900.0, "open_positions": 2},
    ]
    rows = _daily_rows(curve, 25_000.0)
    assert rows[0]["day_pnl"] == pytest.approx(100.0)
    assert rows[1]["day_pnl"] == pytest.approx(-200.0)
    assert rows[1]["cum_pct"] == pytest.approx(-0.4)


def test_sparkline_shape():
    assert _sparkline([1.0, 1.0]) == "▁▁"
    line = _sparkline([0.0, 5.0, 10.0])
    assert line[0] == "▁" and line[-1] == "█"
    assert _sparkline([1.0]) == ""
