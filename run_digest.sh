#!/bin/bash
LOG="/Users/devandesai/Documents/GitHub/Morning-Digest-Project/launchd.log"

echo "=== RUN $(date) ===" >> "$LOG"

# IMPORTANT: use the same python you use in Terminal.
# If `which python3` prints something else, replace /usr/bin/python3 below.
PY="/usr/bin/python3"

$PY /Users/devandesai/Documents/GitHub/Morning-Digest-Project/sports_digest.py >> "$LOG" 2>&1
STATUS=$?

if [ $STATUS -eq 0 ]; then
  /usr/bin/osascript -e 'display notification "✅ Posted to Discord" with title "Morning Digest"'
else
  /usr/bin/osascript -e 'display notification "❌ Failed — check launchd.log" with title "Morning Digest"'
fi

exit $STATUS
