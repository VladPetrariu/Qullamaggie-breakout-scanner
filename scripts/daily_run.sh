#!/bin/zsh
# Daily automated run: pre-market scan → paper simulation.
# Installed as a launchd agent by scripts/install_automation.sh; safe to
# run manually too. Logs to logs/daily_YYYY-MM-DD.log.

set -u
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
exec >> "$LOG_DIR/daily_$(date +%F).log" 2>&1

echo ""
echo "=== Daily run started $(date) ==="

PY="$PROJECT_DIR/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "ERROR: venv python not found at $PY — create it with: python -m venv .venv && pip install -r requirements.txt"
  exit 1
fi
export MPLBACKEND=Agg  # matplotlib must not require a display

# Hold one sleep assertion for the ENTIRE run, retry waits included — a
# lid-closed Mac re-sleeps within a minute of an assertion dropping, which
# would suspend the retry sleeps until the next wake (hours later, past
# the 9:30 ET cutoff). caffeinate exits with us via -w.
caffeinate -i -w $$ &

# Weekend guard for manual invocations (the launchd schedule is weekday-only).
if [[ "$(date +%u)" -gt 5 ]]; then
  echo "Weekend — market closed, nothing to do."
  exit 0
fi

# 1. Scan — writes scans/signals_YYYY-MM-DD.json. Retried because yfinance
#    occasionally throttles.
scan_ok=0
for attempt in 1 2 3; do
  echo "--- Scan attempt $attempt at $(date +%T) ---"
  if "$PY" -m scanner --no-open; then
    scan_ok=1
    break
  fi
  [[ $attempt -lt 3 ]] && { echo "Scan failed; retrying in 5 minutes..."; sleep 300; }
done
[[ $scan_ok -eq 0 ]] && echo "WARNING: scan failed after 3 attempts — no new signals today."

# 2. Paper simulation — processes all completed trading days since the last
#    run (idempotent; catches up any backlog). Runs even if the scan failed.
for attempt in 1 2; do
  echo "--- Paper simulation attempt $attempt at $(date +%T) ---"
  if "$PY" -m scanner --paper; then
    break
  fi
  [[ $attempt -lt 2 ]] && { echo "Paper run failed; retrying in 2 minutes..."; sleep 120; }
done

# Keep 60 days of logs.
find "$LOG_DIR" -name 'daily_*.log' -mtime +60 -delete 2>/dev/null

echo "=== Daily run finished $(date) ==="
