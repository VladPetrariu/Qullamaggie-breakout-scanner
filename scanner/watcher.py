"""Intraday watchlist monitor — polls prices and alerts on breakouts.

Usage: python -m scanner --watch
Loads today's scan JSON, monitors the top N stocks, and alerts when
price approaches or breaks through the breakout level.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime

import yfinance as yf

from .config import SCANS_DIR


_POLL_INTERVAL = 120  # seconds between price checks
_WATCH_LIMIT = 20     # how many top stocks to monitor
_ALERT_THRESHOLD_ATR = 0.5  # alert when within this many ATR of level


def watch():
    """Main watch loop — load today's scan and poll prices."""
    scan = _load_today_scan()
    if scan is None:
        print("  No scan found for today. Run 'python -m scanner' first.")
        sys.exit(1)

    watchlist = scan.get("watchlist", [])[:_WATCH_LIMIT]
    if not watchlist:
        print("  Watchlist is empty.")
        sys.exit(1)

    # Build alert targets
    targets = []
    for stock in watchlist:
        level = stock.get("level_value") or stock.get("breakout_level")
        if level is None:
            continue
        targets.append({
            "ticker": stock["ticker"],
            "level": level,
            "level_type": stock.get("level_label", ""),
            "alerted": False,
        })

    if not targets:
        print("  No stocks with breakout levels to monitor.")
        sys.exit(1)

    tickers_str = ", ".join(t["ticker"] for t in targets)
    print(f"\n  Watching {len(targets)} stocks: {tickers_str}")
    print(f"  Polling every {_POLL_INTERVAL}s. Press Ctrl+C to stop.\n")

    try:
        while True:
            _check_prices(targets)
            time.sleep(_POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n  Stopped watching.")


def _check_prices(targets: list[dict]) -> None:
    """Fetch current prices and check against breakout levels."""
    tickers = [t["ticker"] for t in targets if not t["alerted"]]
    if not tickers:
        print(f"  [{_now()}] All targets alerted. Watching for new breaks...")
        return

    try:
        data = yf.download(tickers, period="1d", progress=False, auto_adjust=True)
    except Exception as e:
        print(f"  [{_now()}] Price fetch error: {e}")
        return

    if data.empty:
        return

    for target in targets:
        if target["alerted"]:
            continue

        ticker = target["ticker"]
        level = target["level"]

        try:
            if len(tickers) == 1:
                price = float(data["Close"].iloc[-1])
            else:
                price = float(data["Close"][ticker].iloc[-1])
        except (KeyError, TypeError, IndexError):
            continue

        if price <= 0:
            continue

        pct_from_level = (level - price) / price * 100

        if price >= level:
            # Breakout!
            _alert(ticker, price, level, "BREAKOUT", target["level_type"])
            target["alerted"] = True
        elif pct_from_level <= 1.0:
            # Within 1% of level
            _alert(ticker, price, level, "APPROACHING", target["level_type"])
            target["alerted"] = True
        else:
            print(f"  [{_now()}] {ticker:>6} ${price:.2f}  →  {pct_from_level:.1f}% below {target['level_type']} ${level:.2f}")


def _alert(ticker: str, price: float, level: float, status: str, level_type: str) -> None:
    """Print alert and send OS notification."""
    msg = f"{ticker} {status}: ${price:.2f} (level: ${level:.2f} {level_type})"
    print(f"\n  *** [{_now()}] {msg} ***\n")
    _notify(f"Breakout Scanner: {ticker}", msg)


def _notify(title: str, message: str) -> None:
    """Send a macOS notification (silent fallback on other platforms)."""
    if platform.system() == "Darwin":
        try:
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{message}" with title "{title}"'],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass


def _load_today_scan() -> dict | None:
    """Load today's scan JSON."""
    today = datetime.now().strftime("%Y-%m-%d")
    path = SCANS_DIR / f"scan_{today}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")
