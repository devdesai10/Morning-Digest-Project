#!/bin/bash
PROJECT_DIR="/Users/devandesai/Documents/GitHub/Morning-Digest-Project"
LOG="$PROJECT_DIR/launchd.log"

echo "=== RUN $(date) ===" >> "$LOG"

# Use the venv python so installed packages (requests, etc.) are available
PY="$PROJECT_DIR/venv/bin/python3"

# Fallback to system python if venv doesn't exist
if [ ! -f "$PY" ]; then
  PY="/usr/bin/python3"
fi

$PY "$PROJECT_DIR/sports_digest.py" >> "$LOG" 2>&1
STATUS=$?

if [ $STATUS -eq 0 ]; then
  /usr/bin/osascript -e 'display notification "✅ Posted to Discord" with title "Morning Digest"'
else
  /usr/bin/osascript -e 'display notification "❌ Failed — check launchd.log" with title "Morning Digest"'
fi

exit $STATUS
