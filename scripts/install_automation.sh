#!/bin/zsh
# Install the daily automation: a launchd agent that runs daily_run.sh
# every weekday at 5:45 AM local time (8:45 AM ET — pre-market for a
# Pacific-time machine; adjust HOUR below if your timezone differs).
#
# The plist is generated here with this machine's paths, so nothing
# machine-specific lives in the repo.
#
# launchd behavior worth knowing:
# - If the Mac is ASLEEP at 5:45, the job fires at the next wake — to run
#   while you sleep, schedule a wake (needs sudo, prints command below).
# - If the Mac is powered OFF or you're logged out, the run is skipped;
#   the next run catches up the paper simulation automatically.

set -eu
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.qullamaggie.daily"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
HOUR=5
MINUTE=45

mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/logs"

{
  cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PROJECT_DIR/scripts/daily_run.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
EOF
  for weekday in 1 2 3 4 5; do
    cat <<EOF
        <dict>
            <key>Weekday</key><integer>$weekday</integer>
            <key>Hour</key><integer>$HOUR</integer>
            <key>Minute</key><integer>$MINUTE</integer>
        </dict>
EOF
  done
  cat <<EOF
    </array>
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/logs/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/logs/launchd.log</string>
</dict>
</plist>
EOF
} > "$PLIST"

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "Installed launchd agent '$LABEL' — weekdays at $HOUR:$(printf '%02d' $MINUTE) local time."
launchctl list | grep "$LABEL" >/dev/null && echo "Agent is loaded."
echo ""
echo "To let it run while the Mac sleeps (lid can be closed, must be plugged"
echo "in, and you must stay logged in), schedule a wake 2 minutes earlier:"
echo ""
echo "    sudo pmset repeat wakeorpoweron MTWRF 0$HOUR:$((MINUTE - 2)):00"
echo ""
echo "Check the current wake schedule with: pmset -g sched"
echo "Test the job now with:               launchctl start $LABEL"
echo "Watch logs at:                       $PROJECT_DIR/logs/"
echo "Uninstall with: launchctl unload \"$PLIST\" && rm \"$PLIST\" && sudo pmset repeat cancel"
