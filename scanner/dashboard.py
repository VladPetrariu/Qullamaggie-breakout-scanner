"""Generate self-contained HTML dashboard from scan results."""

from __future__ import annotations

import json
import webbrowser
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .config import PROJECT_ROOT, SCANS_DIR


_TEMPLATE_DIR = PROJECT_ROOT / "templates"


def generate_dashboard(
    market_context: dict,
    watchlist: list[dict],
    universe_size: int,
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
