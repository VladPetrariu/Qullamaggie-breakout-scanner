"""Tests for the paper-report statistics (pure functions only)."""

import pytest

from scanner.paper_report import (
    _daily_rows,
    _funnel,
    _gate_status,
    _mean_ci_95,
    _sparkline,
    _t_critical_95,
    _trade_stats,
    _trades_needed_2sigma,
    _wilson_ci,
)


def _trade(pnl_dollars, pnl_pct, days=5, reason="time", mae=-2.0, mfe=4.0, ticker="TST", risk_dollars=100.0):
    return {
        "ticker": ticker,
        "pnl_dollars": pnl_dollars,
        "risk_dollars": risk_dollars,
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
    assert s["mean_r"] == pytest.approx((5.0 + 0.97 - 2.5) / 3)
    assert s["r_n"] == 3
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


def test_wilson_ci_brackets_the_point_estimate():
    lo, hi = _wilson_ci(30, 60)
    assert lo < 50.0 < hi
    assert lo == pytest.approx(37.6, abs=0.5)
    assert hi == pytest.approx(62.4, abs=0.5)
    # More trades → tighter interval.
    lo2, hi2 = _wilson_ci(300, 600)
    assert hi2 - lo2 < hi - lo


def test_gate_status_small_sample():
    s = _trade_stats([_trade(+100.0, +5.0)])
    rows = _gate_status(s, max_dd_pct=-1.14)
    by_label = {r[0]: r for r in rows}
    assert by_label["60+ closed trades"][1] is False
    assert by_label["lower 95% bound of mean R > 0"][1] is None
    assert "need 2+" in by_label["lower 95% bound of mean R > 0"][2]
    assert by_label["live mean R consistent with backtest"][1] is None
    # Win rate unjudgeable below 30 trades.
    win_row = [r for r in rows if "win rate" in r[0]][0]
    assert win_row[1] is None
    assert by_label["max drawdown < 10%"][1] is True


def test_gate_status_judges_win_rate_at_30_trades():
    trades = [_trade(+10.0, +1.0)] * 16 + [_trade(-10.0, -1.0)] * 14  # 53.3%
    rows = _gate_status(_trade_stats(trades), -2.0)
    win_row = [r for r in rows if "win rate" in r[0]][0]
    assert win_row[1] is True


def test_gate_status_inconclusive_win_rate_passes():
    # 33% at n=30: the Wilson CI reaches 51% — cannot yet rule out the
    # 47-56% backtest band, so the criterion is not failed.
    trades = [_trade(+10.0, +1.0)] * 10 + [_trade(-10.0, -1.0)] * 20
    rows = _gate_status(_trade_stats(trades), -12.0)
    by_label = {r[0]: r for r in rows}
    win_row = [r for r in rows if "win rate" in r[0]][0]
    assert win_row[1] is True
    # Mean −0.033R; the CI straddles zero, so the edge isn't shown.
    assert by_label["lower 95% bound of mean R > 0"][1] is False
    assert by_label["max drawdown < 10%"][1] is False


def test_gate_status_flags_conclusively_bad_win_rate():
    # 20% over 75 trades: CI tops out around 31% — conclusively below 47%.
    trades = [_trade(+10.0, +1.0)] * 15 + [_trade(-10.0, -1.0)] * 60
    rows = _gate_status(_trade_stats(trades), -12.0)
    win_row = [r for r in rows if "win rate" in r[0]][0]
    assert win_row[1] is False


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


def test_mean_ci_uses_student_t_and_contains_mean():
    values = [-0.5, 0.0, 0.5]
    lo, hi = _mean_ci_95(values)
    assert lo < 0.0 < hi
    assert hi - lo == pytest.approx(2 * 4.303 * 0.5 / (3 ** 0.5))


def test_mean_ci_requires_two_observations():
    assert _mean_ci_95([]) is None
    assert _mean_ci_95([0.25]) is None


def test_trades_needed_2sigma():
    assert _trades_needed_2sigma(0.68, 0.081) == 271
    assert _trades_needed_2sigma(0.68, 0.0) is None


def test_t_critical_95_continues_past_the_table():
    # Exact two-sided 95% values: 2.042 (30 df), 2.0395 (31), 2.0167 (43),
    # 2.0010 (59), 1.9840 (100). No drop to the normal 1.96 after 30 df.
    assert _t_critical_95(30) == 2.042
    assert _t_critical_95(31) == pytest.approx(2.0395, abs=2e-4)
    assert _t_critical_95(43) == pytest.approx(2.0167, abs=2e-4)
    assert _t_critical_95(59) == pytest.approx(2.0010, abs=2e-4)
    assert _t_critical_95(100) == pytest.approx(1.9840, abs=2e-4)
    assert 1.96 < _t_critical_95(10_000) < 1.961


def test_gate_status_positive_edge_requires_lower_ci_above_zero():
    trades = [_trade(25, 1, risk_dollars=100)] * 80
    stats = _trade_stats(trades)
    rows = _gate_status(stats, -2.0)
    by_label = {r[0]: r for r in rows}
    assert by_label["lower 95% bound of mean R > 0"][1] is True
    # +0.25R beats the +0.081R backtest — above it is fine, like win rate.
    assert by_label["live mean R consistent with backtest"][1] is True
    assert not any("SPY" in r[0] for r in rows)


def _r_trades(r_values):
    return [_trade(r * 100.0, r, risk_dollars=100.0) for r in r_values]


def test_gate_status_consistency_passes_when_ci_contains_backtest():
    # Mean 0, wide spread: CI ≈ ±0.25R contains +0.081R; no edge shown.
    stats = _trade_stats(_r_trades([1.0, -1.0] * 30))
    by_label = {r[0]: r for r in _gate_status(stats, -2.0)}
    assert by_label["live mean R consistent with backtest"][1] is True
    assert by_label["lower 95% bound of mean R > 0"][1] is False


def test_gate_status_consistency_fails_when_ci_sits_below_backtest():
    # Mean −0.20R, tight spread over 60 trades: CI tops out near −0.17R.
    stats = _trade_stats(_r_trades([-0.1, -0.3] * 30))
    by_label = {r[0]: r for r in _gate_status(stats, -2.0)}
    assert by_label["live mean R consistent with backtest"][1] is False


def test_gate_status_consistency_waits_for_min_trades():
    stats = _trade_stats(_r_trades([-0.1, -0.3] * 20))  # 40 trades
    row = {r[0]: r for r in _gate_status(stats, -2.0)}["live mean R consistent with backtest"]
    assert row[1] is None
    assert "need 60+" in row[2]


def test_gate_status_sample_size_row_is_informational():
    label = "sample size to resolve observed edge at 2σ"
    positive = {r[0]: r for r in _gate_status(_trade_stats(_r_trades([1.5, -1.0] * 20)), -2.0)}
    assert positive[label][1] is None
    assert "trades at observed mean/std" in positive[label][2]
    # A resolved negative mean is not a ✓: there's no positive edge to resolve.
    negative = {r[0]: r for r in _gate_status(_trade_stats(_r_trades([-0.1, -0.3] * 30)), -2.0)}
    assert negative[label][1] is None
    assert "no positive edge" in negative[label][2]


def test_gate_status_missing_risk_blocks_r_rows():
    trades = _r_trades([0.5, -0.5] * 35) + [_trade(50.0, 2.0, risk_dollars=None)]
    by_label = {r[0]: r for r in _gate_status(_trade_stats(trades), -2.0)}
    for label in ("lower 95% bound of mean R > 0", "live mean R consistent with backtest",
                  "sample size to resolve observed edge at 2σ"):
        assert by_label[label][1] is None
        assert "R unavailable for 1 trade(s)" in by_label[label][2]


def test_trade_stats_missing_risk_does_not_invent_r():
    trades = [_trade(100, 5), _trade(-20, -1, risk_dollars=None)]
    stats = _trade_stats(trades)
    assert stats["r_n"] == 1
    assert stats["trades_missing_risk"] == 1
    assert stats["mean_r"] == pytest.approx(1.0)
    assert stats["mean_r_ci"] is None
