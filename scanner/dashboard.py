"""Generate self-contained HTML dashboard from scan results."""

from __future__ import annotations

import json
import webbrowser
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .config import PROJECT_ROOT, SCANS_DIR


_TEMPLATE_DIR = PROJECT_ROOT / "templates"


def load_prior_scan() -> dict | None:
    """Load the most recent prior scan JSON (before today).

    Returns the parsed JSON dict, or None if no prior scan exists.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    scan_files = sorted(SCANS_DIR.glob("scan_*.json"), reverse=True)
    for path in scan_files:
        date_part = path.stem.replace("scan_", "")
        if date_part < today:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
    return None


def compute_deltas(watchlist: list[dict], prior: dict | None) -> list[dict]:
    """Annotate each stock with rank change and 'new' flag vs prior scan.

    Modifies watchlist in-place and returns it.
    """
    if prior is None:
        return watchlist

    prior_list = prior.get("watchlist", [])
    prior_rank = {s["ticker"]: i for i, s in enumerate(prior_list)}
    prior_data = {s["ticker"]: s for s in prior_list}

    for i, stock in enumerate(watchlist):
        ticker = stock["ticker"]
        if ticker in prior_rank:
            stock["is_new"] = False
            stock["rank_change"] = prior_rank[ticker] - i  # positive = moved up
            # Key factor deltas
            prev = prior_data[ticker]
            stock["delta_rs"] = round(
                stock.get("rs_percentile", 0) - prev.get("rs_percentile", 0), 1
            )
        else:
            stock["is_new"] = True
            stock["rank_change"] = 0
            stock["delta_rs"] = 0

    return watchlist


def generate_dashboard(
    market_context: dict,
    watchlist: list[dict],
    universe_size: int,
    track_record: dict | None = None,
    sector_heat: list[dict] | None = None,
) -> Path:
    """Render the dashboard HTML and return the output path."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=False,
    )
    template = env.get_template("dashboard.html")

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    html = template.render(
        market_context=market_context,
        watchlist_json=json.dumps(watchlist, default=str),
        track_record_json=json.dumps(track_record or {}, default=str),
        sector_heat_json=json.dumps(sector_heat or [], default=str),
        watchlist_count=len(watchlist),
        universe_size=universe_size,
        generated_date=date_str,
        generated_time=time_str,
    )

    output_path = SCANS_DIR / f"scan_{date_str}.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path


def save_scan_json(
    market_context: dict,
    watchlist: list[dict],
) -> Path:
    """Save raw scan results as dated JSON for history."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = SCANS_DIR / f"scan_{date_str}.json"
    payload = {
        "date": date_str,
        "market_context": market_context,
        "watchlist": watchlist,
    }
    path.write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")
    return path


def open_dashboard(path: Path) -> None:
    """Open the dashboard HTML in the default browser."""
    webbrowser.open(f"file://{path.resolve()}")
