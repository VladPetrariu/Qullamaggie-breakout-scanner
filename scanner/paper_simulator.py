"""Local paper-trading simulator (Phase 10, step 52 — Option A).

Consumes the trade signals saved by scanner/signals.py
(scans/signals_YYYY-MM-DD.json) and simulates order execution against
actual daily OHLC bars. No broker, no KYC, no network beyond the same
yfinance data the scanner already uses.

Execution model (one daily bar per decision — no intraday data):
- A signal becomes a one-shot buy order, live for the first trading day
  on/after its signal date (next day if the scan ran after market open).
- Fill rules: if the day's Open gaps past the limit entry by more than
  MAX_ENTRY_OVERSHOOT_PCT the order is abandoned (don't chase). A small
  gap fills at the Open; otherwise the order fills at the limit price
  once the day's High crosses it. Unfilled orders expire — the next
  scan re-issues the signal if the setup is still valid.
- Stops: gap-down opens fill at the Open (not the stop price). If the
  fill day's Low also touches the stop, we assume the worst case and
  exit same-day (daily bars can't prove the dip came before the entry).
- Time exit at the close of the max-hold-days'th trading day after fill.
- Positions are sized at fill time against *current* account equity
  (1% risk, 20% cap, available cash) so compounding stays honest.

State lives in paper_trades/ (gitignored): account.json holds the
account, open positions, pending orders, and equity curve; trades.json
is the append-only closed-trade log.

yfinance returns split/dividend-adjusted history, so a split between
signal date and simulation would silently break price levels. Orders
and positions carry their price basis (last close at signal/mark time)
and get rescaled when the freshly downloaded history disagrees by more
than PAPER_SPLIT_TOLERANCE_PCT.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from datetime import date as dt_date
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from .config import (
    DEFAULT_ACCOUNT_EQUITY,
    MAX_CONCURRENT_POSITIONS,
    MAX_ENTRY_OVERSHOOT_PCT,
    MAX_POSITION_PCT,
    PAPER_DIR,
    PAPER_SPLIT_TOLERANCE_PCT,
    PAPER_STALE_DATA_FORCE_CLOSE_DAYS,
    RISK_PER_TRADE_PCT,
    SCANS_DIR,
)

ET = ZoneInfo("America/New_York")
MARKET_OPEN_ET = dt_time(9, 30)  # scans generated after this (US/Eastern) run next trading day


# ── State persistence ────────────────────────────────────────────────────


def _account_path(paper_dir: Path) -> Path:
    return paper_dir / "account.json"


def _trades_path(paper_dir: Path) -> Path:
    return paper_dir / "trades.json"


def _new_account(equity: float) -> dict:
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "starting_equity": equity,
        "cash": equity,
        "last_processed_date": None,
        "processed_signal_files": {},  # filename -> content sha1
        "pending_orders": [],
        "open_positions": [],
        "order_history": [],
        "equity_curve": [],
    }


def _load_account(paper_dir: Path, equity: float | None) -> dict:
    path = _account_path(paper_dir)
    if path.exists():
        with open(path) as f:
            state = json.load(f)
        if isinstance(state.get("processed_signal_files"), list):
            # pre-hash account format
            state["processed_signal_files"] = {
                name: "" for name in state["processed_signal_files"]
            }
        if equity is not None and equity != state["starting_equity"]:
            print(
                f"  Note: --equity ignored — account already exists with "
                f"${state['starting_equity']:,.0f} starting equity "
                f"(use --paper-reset to start over)"
            )
        return state
    return _new_account(equity if equity is not None else DEFAULT_ACCOUNT_EQUITY)


def _write_json_atomic(path: Path, payload) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)


def _save_account(paper_dir: Path, state: dict) -> None:
    paper_dir.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(_account_path(paper_dir), state)


def _load_trades(paper_dir: Path) -> list[dict]:
    path = _trades_path(paper_dir)
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def _save_trades(paper_dir: Path, trades: list[dict]) -> None:
    paper_dir.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(_trades_path(paper_dir), trades)


# ── Signal file ingestion ────────────────────────────────────────────────


def _earliest_active_date(
    file_date: dt_date, generated_at: str, local_tz=None
) -> dt_date:
    """First calendar date the order may trade. Scans generated before the
    9:30 US/Eastern open trade the same day; anything later — including
    intraday runs — trades the next day, otherwise the simulator would fill
    against hours of the bar that predate the signal. generated_at is a
    naive machine-local timestamp, so attach the local zone and convert."""
    try:
        gen = datetime.fromisoformat(generated_at)
    except (ValueError, TypeError):
        return file_date
    if gen.tzinfo is None:
        gen = gen.replace(tzinfo=local_tz or datetime.now().astimezone().tzinfo)
    market_open = datetime.combine(file_date, MARKET_OPEN_ET, tzinfo=ET)
    if gen.astimezone(ET) >= market_open:
        return file_date + timedelta(days=1)
    return file_date


def _collect_new_orders(scans_dir: Path, state: dict) -> list[dict]:
    """Read new or changed signals_*.json files into pending orders.

    Files are tracked by content hash, so re-running the scan (which
    overwrites today's file) replaces its not-yet-simulated orders instead
    of being silently ignored. Once any of a file's orders has simulated,
    a changed file is reported but the original results stand."""
    orders: list[dict] = []
    seen: dict = state["processed_signal_files"]
    for path in sorted(scans_dir.glob("signals_*.json")):
        try:
            raw = path.read_bytes()
            payload = json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  Warning: could not read {path.name}: {exc}")
            continue
        digest = hashlib.sha1(raw).hexdigest()
        file_date = dt_date.fromisoformat(path.stem.replace("signals_", ""))
        stored = seen.get(path.name)
        if stored is not None:
            if stored in ("", digest):
                seen[path.name] = digest
                continue
            consumed = any(
                h.get("signal_date") == file_date.isoformat()
                for h in state["order_history"]
            )
            if consumed:
                print(
                    f"  Warning: {path.name} changed after its orders were "
                    f"already simulated — keeping the original results"
                )
                seen[path.name] = digest
                continue
            before = len(state["pending_orders"])
            # Slice-assign to filter in place — callers hold a reference to
            # this list and extend it after we return.
            state["pending_orders"][:] = [
                o for o in state["pending_orders"]
                if o["signal_date"] != file_date.isoformat()
            ]
            print(
                f"  {path.name} was regenerated — replacing "
                f"{before - len(state['pending_orders'])} pending order(s)"
            )
        seen[path.name] = digest
        file_orders: list[dict] = []
        for sig in payload.get("signals", []):
            active = _earliest_active_date(file_date, sig.get("generated_at", ""))
            last_done = state["last_processed_date"]
            if last_done is not None and active.isoformat() <= last_done:
                state["order_history"].append({
                    "date": active.isoformat(),
                    "ticker": sig["ticker"],
                    "signal_date": file_date.isoformat(),
                    "status": "stale",
                    "detail": "signal file discovered after its trade day was already simulated",
                })
                continue
            file_orders.append({
                "ticker": sig["ticker"],
                "rank": sig.get("rank", 99),
                "level_type": sig.get("level_type", "unknown"),
                "signal_date": file_date.isoformat(),
                "activation_date": active.isoformat(),
                "limit_entry": float(sig["limit_entry"]),
                "stop_price": float(sig["stop_price"]),
                "signal_last_close": float(sig["last_close"]),
                "max_hold_days": int(sig.get("max_hold_days", 10)),
            })

        # A newer signal supersedes a still-pending order for the same
        # ticker when both target the same trade day or later (e.g. a
        # post-close scan and the next morning's pre-market scan both
        # signal it) — the freshest view of the setup wins. A pending
        # order with an EARLIER trade day keeps its shot; if it fills,
        # the duplicate-ticker guard blocks the newer order. The incoming
        # file must be strictly newer than the pending order's origin —
        # an older file discovered late (e.g. after a transient read
        # failure) must never displace a fresher order. Weekend/holiday
        # collisions that this calendar-date comparison can't see are
        # resolved at simulation time in _process_day.
        new_activation = {o["ticker"]: o["activation_date"] for o in file_orders}

        def _is_superseded(o: dict) -> bool:
            t = o["ticker"]
            return (
                t in new_activation
                and o["activation_date"] >= new_activation[t]
                and o["signal_date"] < file_date.isoformat()
            )

        superseded = [
            o for o in orders + state["pending_orders"] if _is_superseded(o)
        ]
        for old in superseded:
            state["order_history"].append({
                "date": old["activation_date"],
                "ticker": old["ticker"],
                "signal_date": old["signal_date"],
                "status": "superseded",
                "detail": f"newer signal in {path.name}",
            })
        if superseded:
            print(f"  {len(superseded)} pending order(s) superseded by {path.name}")
        orders[:] = [o for o in orders if not _is_superseded(o)]
        state["pending_orders"][:] = [
            o for o in state["pending_orders"] if not _is_superseded(o)
        ]
        orders.extend(file_orders)

        n = payload.get("summary", {}).get("signals_issued", 0)
        print(f"  Loaded {path.name}: {n} signal(s)")
    return orders


# ── Price data ───────────────────────────────────────────────────────────


def _period_for(earliest: dt_date, today: dt_date) -> str:
    span = (today - earliest).days
    if span <= 100:
        return "6mo"
    if span <= 320:
        return "1y"
    if span <= 680:
        return "2y"
    return "5y"


def _default_fetch(tickers: list[str], period: str) -> dict[str, pd.DataFrame]:
    """Download a handful of tickers directly. Deliberately bypasses the
    Cache used by download_prices(): the shared per-period cache files
    hold the whole universe, and overwriting one with a 10-ticker subset
    would poison a later backtest run on the same day."""
    from .data import _download_chunk

    return _download_chunk(sorted(set(tickers)), period)


def _normalize_frames(data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    out = {}
    for ticker, df in data.items():
        clean = df.copy()
        clean.index = pd.DatetimeIndex(clean.index).normalize()
        out[ticker] = clean[~clean.index.duplicated(keep="last")].sort_index()
    return out


def _close_on_or_before(df: pd.DataFrame, day: dt_date) -> float | None:
    """Last available Close at or before *day*."""
    sliced = df.loc[: pd.Timestamp(day)]
    if sliced.empty:
        return None
    return float(sliced["Close"].iloc[-1])


# ── Split / adjustment rescaling ─────────────────────────────────────────


def _basis_factor(known_close: float, fresh_close: float | None) -> float | None:
    """Ratio between freshly downloaded history and a stored price basis.
    Returns None when within tolerance (no rescale needed)."""
    if fresh_close is None or known_close <= 0:
        return None
    factor = fresh_close / known_close
    if abs(factor - 1) * 100 <= PAPER_SPLIT_TOLERANCE_PCT:
        return None
    return factor


def _rescale_order(order: dict, factor: float) -> None:
    order["limit_entry"] = round(order["limit_entry"] * factor, 4)
    order["stop_price"] = round(order["stop_price"] * factor, 4)
    order["signal_last_close"] = round(order["signal_last_close"] * factor, 4)


def _rescale_position(pos: dict, factor: float) -> float:
    """Adjust a held position to a new price basis (e.g. a 2:1 split halves
    prices and doubles shares). Fractional shares can't be held, so the
    remainder is settled like a broker's cash-in-lieu — the returned cash
    amount keeps total value exactly invariant."""
    exact_shares = pos["shares"] / factor
    new_shares = int(math.floor(exact_shares))
    new_mark = pos["last_mark_close"] * factor
    cash_in_lieu = (exact_shares - new_shares) * new_mark
    pos["shares"] = new_shares
    pos["fill_price"] = round(pos["fill_price"] * factor, 4)
    pos["stop_price"] = round(pos["stop_price"] * factor, 4)
    pos["last_mark_close"] = round(new_mark, 4)
    return cash_in_lieu


# ── Core mechanics (unit-tested) ─────────────────────────────────────────


def _attempt_fill(order: dict, bar: pd.Series) -> tuple[float | None, str]:
    """Try to fill a one-shot buy order against one daily bar.
    Returns (fill_price, status) — fill_price is None unless status == 'filled'."""
    limit = order["limit_entry"]
    open_ = float(bar["Open"])
    high = float(bar["High"])
    max_chase = limit * (1 + MAX_ENTRY_OVERSHOOT_PCT / 100)

    if open_ >= limit:
        if open_ > max_chase:
            return None, "gapped_past_entry"
        return open_, "filled"
    if high >= limit:
        return limit, "filled"
    return None, "not_triggered"


def _size_position(
    equity: float, cash: float, fill_price: float, stop_price: float
) -> tuple[int, float]:
    """Shares for a new position: 1% equity risk over the stop distance,
    capped at 20% of equity and at available cash. Returns (shares, risk$)."""
    stop_distance = fill_price - stop_price
    if stop_distance <= 0 or fill_price <= 0:
        return 0, 0.0
    risk_dollars = equity * RISK_PER_TRADE_PCT
    by_risk = risk_dollars / stop_distance
    by_cap = equity * MAX_POSITION_PCT / fill_price
    by_cash = cash / fill_price
    shares = int(math.floor(min(by_risk, by_cap, by_cash)))
    return max(shares, 0), round(risk_dollars, 2)


def _check_exit(pos: dict, bar: pd.Series) -> tuple[float, str] | None:
    """Exit decision for one open position against one daily bar (a bar
    *after* the fill day — same-day stops are handled at fill time).
    Stop first, then time exit at the close. Returns (exit_price, reason)."""
    open_ = float(bar["Open"])
    low = float(bar["Low"])
    close = float(bar["Close"])
    stop = pos["stop_price"]

    if open_ <= stop:
        return open_, "stop_gap"
    if low <= stop:
        return stop, "stop"
    if pos["days_held"] + 1 >= pos["max_hold_days"]:
        return close, "time"
    return None


# ── Engine ───────────────────────────────────────────────────────────────


def _record_order(state: dict, day: dt_date, order: dict, status: str, detail: str = "") -> None:
    entry = {
        "date": day.isoformat(),
        "ticker": order["ticker"],
        "signal_date": order["signal_date"],
        "status": status,
    }
    if detail:
        entry["detail"] = detail
    state["order_history"].append(entry)


def _close_position(
    state: dict,
    trades: list[dict],
    pos: dict,
    day: dt_date,
    exit_price: float,
    reason: str,
) -> None:
    proceeds = pos["shares"] * exit_price
    pnl = proceeds - pos["shares"] * pos["fill_price"]
    state["cash"] += proceeds
    trades.append({
        "ticker": pos["ticker"],
        "rank": pos["rank"],
        "level_type": pos["level_type"],
        "signal_date": pos["signal_date"],
        "fill_date": pos["fill_date"],
        "exit_date": day.isoformat(),
        "fill_price": round(pos["fill_price"], 4),
        "exit_price": round(exit_price, 4),
        "shares": pos["shares"],
        "stop_price": round(pos["stop_price"], 4),
        "risk_dollars": pos["risk_dollars"],
        "pnl_dollars": round(pnl, 2),
        "pnl_pct": round((exit_price / pos["fill_price"] - 1) * 100, 3),
        "days_held": pos["days_held"],
        "exit_reason": reason,
        "mae_pct": round(pos["mae_pct"], 3),
        "mfe_pct": round(pos["mfe_pct"], 3),
    })
    state["open_positions"] = [
        p for p in state["open_positions"] if p is not pos
    ]


def _process_day(
    state: dict,
    trades: list[dict],
    day: dt_date,
    data: dict[str, pd.DataFrame],
    equity_before: float,
) -> float:
    """Simulate one trading day: exits, then entries, then mark-to-market.
    Returns end-of-day equity."""
    ts = pd.Timestamp(day)

    def bar_for(ticker: str) -> pd.Series | None:
        df = data.get(ticker)
        if df is None or ts not in df.index:
            return None
        return df.loc[ts]

    # 1. Exits — free slots and cash before considering new entries.
    for pos in list(state["open_positions"]):
        df = data.get(pos["ticker"])
        if df is None:
            # Ticker entirely absent from this run's download — that's a
            # fetch failure, not a delisting. Carry the position untouched
            # rather than counting toward the data_missing force-close.
            continue
        if ts not in df.index:
            pos["missing_days"] += 1
            if pos["missing_days"] >= PAPER_STALE_DATA_FORCE_CLOSE_DAYS:
                _close_position(
                    state, trades, pos, day, pos["last_mark_close"], "data_missing"
                )
            continue
        bar = df.loc[ts]
        pos["missing_days"] = 0

        exit_decision = _check_exit(pos, bar)
        # Excursion stats must not include price action after the exit: a
        # gap-stop dies at the Open, and a stop exit's worst experienced
        # price is the stop itself (the bar's high may have printed after).
        ref_low, ref_high = float(bar["Low"]), float(bar["High"])
        if exit_decision is not None:
            price, reason = exit_decision
            if reason == "stop_gap":
                ref_low = ref_high = float(bar["Open"])
            elif reason == "stop":
                ref_low, ref_high = price, None
        pos["mae_pct"] = min(pos["mae_pct"], (ref_low / pos["fill_price"] - 1) * 100)
        if ref_high is not None:
            pos["mfe_pct"] = max(
                pos["mfe_pct"], (ref_high / pos["fill_price"] - 1) * 100
            )

        pos["days_held"] += 1
        if exit_decision is not None:
            _close_position(state, trades, pos, day, price, reason)
        else:
            pos["last_mark_close"] = float(bar["Close"])
            pos["last_mark_date"] = day.isoformat()

    # 2. Entries — orders whose activation date has arrived run once, in
    # rank order, then leave the book whatever the outcome.
    due = [
        o for o in state["pending_orders"]
        if dt_date.fromisoformat(o["activation_date"]) <= day
    ]

    # When several pending orders for the SAME ticker come due together —
    # e.g. a Friday post-close signal (activation Saturday) and Monday's
    # pre-market signal both first tradable on Monday — only the freshest
    # signal runs. The real trading calendar decides these collisions,
    # which ingestion-time date comparison can't see across weekends and
    # holidays.
    freshest: dict[str, dict] = {}
    for o in due:
        cur = freshest.get(o["ticker"])
        if cur is None:
            freshest[o["ticker"]] = o
        else:
            loser, winner = (cur, o) if o["signal_date"] > cur["signal_date"] else (o, cur)
            freshest[o["ticker"]] = winner
            state["pending_orders"].remove(loser)
            _record_order(
                state, day, loser, "superseded",
                f"newer signal dated {winner['signal_date']} due the same day",
            )

    for order in sorted(freshest.values(), key=lambda o: (o["activation_date"], o["rank"])):
        state["pending_orders"].remove(order)
        ticker = order["ticker"]
        df = data.get(ticker)
        bar = bar_for(ticker)
        if df is None or bar is None:
            _record_order(state, day, order, "no_data")
            continue

        # Rescale if downloaded (split-adjusted) history disagrees with the
        # price basis the signal was generated from. The signal's last_close
        # belongs to the last completed session before activation — for a
        # pre-market scan that's the day before the file date, for a
        # post-close scan it's the file date itself.
        basis_day = dt_date.fromisoformat(order["activation_date"]) - timedelta(days=1)
        factor = _basis_factor(
            order["signal_last_close"], _close_on_or_before(df, basis_day)
        )
        if factor is not None:
            _rescale_order(order, factor)

        if any(p["ticker"] == ticker for p in state["open_positions"]):
            _record_order(state, day, order, "skipped_already_holding")
            continue
        if len(state["open_positions"]) >= MAX_CONCURRENT_POSITIONS:
            _record_order(state, day, order, "skipped_no_slot")
            continue

        fill_price, status = _attempt_fill(order, bar)
        if fill_price is None:
            _record_order(state, day, order, status)
            continue

        shares, risk_dollars = _size_position(
            equity_before, state["cash"], fill_price, order["stop_price"]
        )
        if shares <= 0:
            _record_order(state, day, order, "skipped_insufficient_cash")
            continue

        state["cash"] -= shares * fill_price
        pos = {
            "ticker": ticker,
            "rank": order["rank"],
            "level_type": order["level_type"],
            "signal_date": order["signal_date"],
            "fill_date": day.isoformat(),
            "fill_price": fill_price,
            "shares": shares,
            "stop_price": order["stop_price"],
            "max_hold_days": order["max_hold_days"],
            "days_held": 0,
            "risk_dollars": risk_dollars,
            "mae_pct": (float(bar["Low"]) / fill_price - 1) * 100,
            "mfe_pct": (float(bar["High"]) / fill_price - 1) * 100,
            "last_mark_close": float(bar["Close"]),
            "last_mark_date": day.isoformat(),
            "missing_days": 0,
        }
        state["open_positions"].append(pos)
        _record_order(state, day, order, "filled", f"{shares} @ {fill_price:.2f}")

        # Same-day stop: the daily bar can't prove the low came before the
        # breakout, so assume the worst and take the stop. Excursion stats
        # reflect only what the trade provably experienced.
        if float(bar["Low"]) <= pos["stop_price"]:
            pos["mae_pct"] = (pos["stop_price"] / fill_price - 1) * 100
            pos["mfe_pct"] = 0.0
            _close_position(
                state, trades, pos, day, pos["stop_price"], "stop_same_day"
            )

    # 3. Mark to market.
    market_value = sum(
        p["shares"] * p["last_mark_close"] for p in state["open_positions"]
    )
    equity = state["cash"] + market_value
    state["equity_curve"].append({
        "date": day.isoformat(),
        "equity": round(equity, 2),
        "cash": round(state["cash"], 2),
        "open_positions": len(state["open_positions"]),
    })
    return equity


def _rescale_held_positions(
    state: dict, trades: list[dict], data: dict[str, pd.DataFrame]
) -> None:
    """Detect splits that happened while a position was held across runs:
    compare each position's stored mark against the fresh history's close
    for that same date. Fractional remainders settle to cash; a position
    reduced to zero shares (odd-lot reverse split) is cashed out entirely."""
    for pos in list(state["open_positions"]):
        df = data.get(pos["ticker"])
        if df is None or not pos.get("last_mark_date"):
            continue
        mark_date = dt_date.fromisoformat(pos["last_mark_date"])
        fresh = _close_on_or_before(df, mark_date)
        factor = _basis_factor(pos["last_mark_close"], fresh)
        if factor is not None:
            print(
                f"  Note: {pos['ticker']} price basis shifted ×{factor:.4g} "
                f"(split/adjustment) — position rescaled"
            )
            state["cash"] += _rescale_position(pos, factor)
            if pos["shares"] <= 0:
                _close_position(
                    state, trades, pos, mark_date, pos["last_mark_close"],
                    "split_cashout",
                )


# ── Public entry points ──────────────────────────────────────────────────


def run_paper_simulator(
    *,
    equity: float | None = None,
    paper_dir: Path = PAPER_DIR,
    scans_dir: Path = SCANS_DIR,
    fetch_prices=None,
    today: dt_date | None = None,
) -> dict:
    """Process all pending signals and open positions up to yesterday's
    close, persist state, and print an account report. Returns the state
    (for tests)."""
    print()
    print("  Paper Trading Simulator")
    print("  " + "=" * 40)
    print()

    fetch = fetch_prices or _default_fetch
    today = today or dt_date.today()
    state = _load_account(paper_dir, equity)
    trades = _load_trades(paper_dir)

    state["pending_orders"].extend(_collect_new_orders(scans_dir, state))

    if not state["pending_orders"] and not state["open_positions"]:
        print("  Nothing to simulate — no pending orders or open positions.")
        _save_account(paper_dir, state)
        _print_report(state, trades)
        return state

    # Simulate from the day after the last processed one (or the earliest
    # order activation) through yesterday — today's bar is still forming.
    activations = [
        dt_date.fromisoformat(o["activation_date"]) for o in state["pending_orders"]
    ]
    if state["last_processed_date"] is not None:
        start = dt_date.fromisoformat(state["last_processed_date"]) + timedelta(days=1)
    else:
        start = min(activations)
    end = today - timedelta(days=1)

    if start > end:
        print("  Up to date — no completed trading days to simulate yet.")
        _save_account(paper_dir, state)
        _print_report(state, trades)
        return state

    tickers = (
        {o["ticker"] for o in state["pending_orders"]}
        | {p["ticker"] for p in state["open_positions"]}
        | {"SPY"}
    )
    earliest_basis = min([start] + activations) - timedelta(days=14)
    period = _period_for(earliest_basis, today)
    print(f"  Downloading daily bars for {len(tickers)} tickers ({period})...")
    data = _normalize_frames(fetch(sorted(tickers), period))

    if "SPY" not in data or data["SPY"].empty:
        print("  ERROR: could not download SPY (trading calendar) — aborting, state unchanged.")
        sys.exit(1)

    _rescale_held_positions(state, trades, data)

    calendar = [
        d.date()
        for d in data["SPY"].index
        if start <= d.date() <= end
    ]
    if not calendar:
        print("  Up to date — no completed trading days to simulate yet.")
        _save_account(paper_dir, state)
        _print_report(state, trades)
        return state

    print(f"  Simulating {len(calendar)} trading days ({calendar[0]} → {calendar[-1]})...")
    equity = (
        state["equity_curve"][-1]["equity"]
        if state["equity_curve"]
        else state["starting_equity"]
    )
    for day in calendar:
        equity = _process_day(state, trades, day, data, equity)

    state["last_processed_date"] = calendar[-1].isoformat()
    # Trades first, account last: account.json is the commit point, so a
    # crash between the two re-simulates (visible duplicates) rather than
    # silently losing closed trades.
    _save_trades(paper_dir, trades)
    _save_account(paper_dir, state)
    _print_report(state, trades)
    return state


def print_status(*, paper_dir: Path = PAPER_DIR) -> None:
    """Print the saved account state without simulating anything."""
    if not _account_path(paper_dir).exists():
        print()
        print("  No paper account yet — run `python -m scanner --paper` first.")
        print()
        return
    state = _load_account(paper_dir, None)
    trades = _load_trades(paper_dir)
    _print_report(state, trades)


def reset_account(*, paper_dir: Path = PAPER_DIR) -> None:
    """Delete the paper account and trade log."""
    removed = []
    for path in (_account_path(paper_dir), _trades_path(paper_dir)):
        if path.exists():
            path.unlink()
            removed.append(path.name)
    print()
    if removed:
        print(f"  Paper account reset — deleted {', '.join(removed)}.")
    else:
        print("  No paper account to reset.")
    print()


# ── Reporting ────────────────────────────────────────────────────────────


def _max_drawdown_pct(curve: list[dict], starting_equity: float) -> float:
    # Seed the peak with inception equity — an account that only declines
    # must report its full drawdown (this number feeds the go-live gate).
    peak, worst = starting_equity, 0.0
    for point in curve:
        peak = max(peak, point["equity"])
        if peak > 0:
            worst = min(worst, (point["equity"] / peak - 1) * 100)
    return worst


def _print_report(state: dict, trades: list[dict]) -> None:
    equity = (
        state["equity_curve"][-1]["equity"]
        if state["equity_curve"]
        else state["starting_equity"]
    )
    total_ret = (equity / state["starting_equity"] - 1) * 100
    as_of = state["last_processed_date"] or "—"

    print()
    print("  " + "=" * 92)
    print("  PAPER ACCOUNT")
    print("  " + "=" * 92)
    print(
        f"  Equity ${equity:,.2f} ({total_ret:+.2f}%)   "
        f"Cash ${state['cash']:,.2f}   "
        f"Open {len(state['open_positions'])}/{MAX_CONCURRENT_POSITIONS}   "
        f"Max DD {_max_drawdown_pct(state['equity_curve'], state['starting_equity']):.2f}%   "
        f"As of {as_of}"
    )

    if trades:
        wins = [t for t in trades if t["pnl_dollars"] > 0]
        realized = sum(t["pnl_dollars"] for t in trades)
        print(
            f"  Closed trades: {len(trades)} ({len(wins)}W/{len(trades) - len(wins)}L, "
            f"{len(wins) / len(trades) * 100:.0f}% win rate)   "
            f"Realized P&L ${realized:+,.2f}"
        )

    if state["open_positions"]:
        print()
        print("  OPEN POSITIONS")
        print(
            f"  {'Ticker':>7} {'Filled':>11} {'Entry':>9} {'Last':>9} "
            f"{'Stop':>9} {'Days':>5} {'Unreal $':>10} {'Unreal %':>9}"
        )
        for p in state["open_positions"]:
            unreal = (p["last_mark_close"] - p["fill_price"]) * p["shares"]
            unreal_pct = (p["last_mark_close"] / p["fill_price"] - 1) * 100
            print(
                f"  {p['ticker']:>7} {p['fill_date']:>11} {p['fill_price']:>9.2f} "
                f"{p['last_mark_close']:>9.2f} {p['stop_price']:>9.2f} "
                f"{p['days_held']:>5} {unreal:>+10.2f} {unreal_pct:>+8.2f}%"
            )

    if trades:
        print()
        print("  CLOSED TRADES (most recent 10)")
        print(
            f"  {'Ticker':>7} {'Filled':>11} {'Exited':>11} {'Entry':>9} {'Exit':>9} "
            f"{'Days':>5} {'P&L $':>10} {'P&L %':>8}  Reason"
        )
        for t in trades[-10:]:
            print(
                f"  {t['ticker']:>7} {t['fill_date']:>11} {t['exit_date']:>11} "
                f"{t['fill_price']:>9.2f} {t['exit_price']:>9.2f} {t['days_held']:>5} "
                f"{t['pnl_dollars']:>+10.2f} {t['pnl_pct']:>+7.2f}%  {t['exit_reason']}"
            )

    pending = state["pending_orders"]
    if pending:
        print()
        print("  PENDING ORDERS")
        for o in sorted(pending, key=lambda o: (o["activation_date"], o["rank"])):
            print(
                f"  {o['ticker']:>7}  active {o['activation_date']}  "
                f"limit {o['limit_entry']:.2f}  stop {o['stop_price']:.2f}"
            )

    recent_orders = [
        o for o in state["order_history"] if o["status"] != "filled"
    ][-8:]
    if recent_orders:
        print()
        print("  RECENT UNFILLED/SKIPPED ORDERS")
        for o in recent_orders:
            detail = f" ({o['detail']})" if o.get("detail") else ""
            print(f"  {o['ticker']:>7}  {o['date']}  {o['status']}{detail}")
    print()
