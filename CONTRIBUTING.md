# Contributing

Thanks for your interest in improving the scanner! Contributions of all sizes are welcome — bug reports, factor ideas, tests, docs, and code.

## Ways to contribute

- **Bug reports** — especially around yfinance data quirks, edge cases in factor math, or the paper simulator's fill logic
- **Factor ideas** — new signals or refinements to existing ones (see the golden rule below)
- **Platform support** — daily automation currently targets macOS launchd; Linux cron / systemd and Windows Task Scheduler ports are very welcome
- **Tests** — the paper simulator and report are covered; the factor modules and backtest engine could use more
- **Docs** — anything that was confusing when you set the project up

## Dev setup

```bash
git clone https://github.com/VladPetrariu/Qullamaggie-breakout-scanner.git
cd Qullamaggie-breakout-scanner
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # pytest
python -m pytest tests/               # should pass before and after your change
```

The first full scan (`python -m scanner`) downloads ~4 minutes of data; cached re-runs take ~15 seconds. You don't need a brokerage account for anything — the paper simulator runs entirely on local data.

## Project conventions

- **All thresholds and constants live in `scanner/config.py`** — never hardcode a magic number in a factor module.
- **Factor modules return plain dicts.** Universe-wide factors (relative strength, market context) take `(price_data, universe)`; per-stock factors take `(ticker, df)`.
- **No composite scores.** The dashboard shows raw values only — the ranking sorts by them, but we never collapse factors into a single opaque number.
- **No lookahead in backtests.** Walk-forward only: for each simulated day, factors may use only data available up to that day.
- yfinance `period="1y"` returns ~250 trading days, not 252 — don't hardcode 252 as a minimum.
- Cache keys are date-stamped (e.g. `prices_2026-04-10.parquet`).

## The golden rule: changes to ranking or factors need backtest evidence

This project's ranking system went through five versions, and every change was kept or reverted based on walk-forward backtest results (the journey from 45.9% to 52.4% win rate is documented in the README). The same standard applies to contributions:

- If your PR touches **ranking logic, factor math, or signal generation**, run `python -m scanner --backtest` before and after, and include both result tables in the PR description.
- For bigger claims, run `--backtest-multi` (6 windows across 3 years) — single-window improvements often don't hold up.
- Changes that "feel right" but flatten or reduce the measured edge will be declined, no matter how reasonable they sound. That's not personal — it's the whole methodology.

Pure refactors, bug fixes, docs, and tooling changes don't need backtest runs — just `pytest`.

## Pull requests

1. Branch off `main`, keep the change focused on one thing.
2. Make sure `python -m pytest tests/` passes.
3. Update the README if user-facing behavior changes.
4. In the PR description, say *why* — for factor/ranking changes, that means numbers.

## Reporting bugs

Open an issue with:

- The exact command you ran and the full traceback
- Python version and OS
- Whether it reproduces after deleting the day's cache files in `cache/`

Known non-bugs: occasional yfinance throttling on the first full download is normal — the scanner retries; just run it again.

## Disclaimer

This is a research and screening tool, not financial advice. Contributions to signal or sizing logic are shared under the MIT license with no warranty — nobody involved is responsible for trading outcomes.
