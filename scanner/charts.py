"""Generate inline mini candlestick charts for dashboard cards.

Produces base64-encoded PNG sparklines (60 days, dark theme) showing:
- Candlestick bodies (green up, red down)
- 10/20/50 EMA lines
- Breakout level as a horizontal dashed line
- Volume bars along the bottom
"""

from __future__ import annotations

import base64
from io import BytesIO

import matplotlib
matplotlib.use("Agg")  # non-interactive backend

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd


# Chart dimensions and colors (dark theme matching dashboard)
_WIDTH = 3.2      # inches
_HEIGHT = 1.6
_DPI = 120
_BG = "#1a1a1a"
_BORDER = "#2a2a2a"
_UP = "#22c55e"
_DOWN = "#ef4444"
_WICK = "#666"
_EMA_COLORS = {10: "#3b82f6", 20: "#eab308", 50: "#a855f7"}
_VOL_COLOR = "#333"
_LEVEL_COLOR = "#888"

_CHART_DAYS = 60


def generate_chart(
    df: pd.DataFrame,
    breakout_level: float | None = None,
) -> str | None:
    """Generate a mini candlestick chart and return as a base64 data URI.

    Returns None if there's not enough data.
    """
    if len(df) < 30:
        return None

    tail = df.tail(_CHART_DAYS).copy()
    if len(tail) < 10:
        return None

    fig, (ax, ax_vol) = plt.subplots(
        2, 1,
        figsize=(_WIDTH, _HEIGHT),
        dpi=_DPI,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.05},
        facecolor=_BG,
    )
    ax.set_facecolor(_BG)
    ax_vol.set_facecolor(_BG)

    # Convert dates to numeric for plotting
    dates = mdates.date2num(tail.index.to_pydatetime())
    opens = tail["Open"].values
    highs = tail["High"].values
    lows = tail["Low"].values
    closes = tail["Close"].values
    volumes = tail["Volume"].values

    bar_width = 0.6

    # ── Candlesticks ──────────────────────────────────
    up = closes >= opens
    down = ~up

    # Wicks
    ax.vlines(dates[up], lows[up], highs[up], color=_UP, linewidth=0.5)
    ax.vlines(dates[down], lows[down], highs[down], color=_DOWN, linewidth=0.5)

    # Bodies
    ax.bar(dates[up], closes[up] - opens[up], bar_width, bottom=opens[up],
           color=_UP, edgecolor=_UP, linewidth=0)
    ax.bar(dates[down], opens[down] - closes[down], bar_width, bottom=closes[down],
           color=_DOWN, edgecolor=_DOWN, linewidth=0)

    # ── EMA lines ─────────────────────────────────────
    close_full = df["Close"]
    for period, color in _EMA_COLORS.items():
        ema = close_full.ewm(span=period, adjust=False).mean()
        ema_tail = ema.tail(_CHART_DAYS)
        ema_dates = mdates.date2num(ema_tail.index.to_pydatetime())
        ax.plot(ema_dates, ema_tail.values, color=color, linewidth=0.8, alpha=0.7)

    # ── Breakout level ────────────────────────────────
    if breakout_level is not None:
        ax.axhline(y=breakout_level, color=_LEVEL_COLOR, linewidth=0.7,
                   linestyle="--", alpha=0.6)

    # ── Volume bars ───────────────────────────────────
    vol_colors = [_UP if c >= o else _DOWN for c, o in zip(closes, opens)]
    ax_vol.bar(dates, volumes, bar_width, color=vol_colors, alpha=0.4)

    # ── Styling ───────────────────────────────────────
    for a in (ax, ax_vol):
        a.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
        for spine in a.spines.values():
            spine.set_visible(False)
        a.margins(x=0.01)

    # Tight layout
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

    # ── Encode to base64 ─────────────────────────────
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.02,
                facecolor=_BG, edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def generate_charts_batch(
    watchlist: list[dict],
    price_data: dict[str, pd.DataFrame],
    limit: int = 50,
) -> dict[str, str]:
    """Generate charts for the top *limit* stocks in the watchlist.

    Returns {ticker: data_uri}.
    """
    charts: dict[str, str] = {}
    for stock in watchlist[:limit]:
        ticker = stock["ticker"]
        df = price_data.get(ticker)
        if df is None:
            continue
        level = stock.get("breakout_level") or stock.get("level_value")
        uri = generate_chart(df, breakout_level=level)
        if uri:
            charts[ticker] = uri
    return charts
