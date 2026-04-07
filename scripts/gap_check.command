#!/bin/bash
# Gap Check — double-click this file in Finder to run it in Terminal.
# Compares an upstream GitHub repo against the last-checked state and
# prints a structured report you can paste into the assistant for gap analysis.

# Move to the project root (one level above this scripts/ folder)
cd "$(dirname "$0")/.." || { echo "Could not find project root"; read -rn1; exit 1; }

# Find Python — prefer the project venv, fall back to system python3
PYTHON=".venv/bin/python3"
if [ ! -x "$PYTHON" ]; then
    PYTHON="$(command -v python3 2>/dev/null)"
fi
if [ -z "$PYTHON" ]; then
    echo "Error: python3 not found. Install Python 3.11+ and try again."
    echo ""
    echo "Press any key to close..."
    read -rn1
    exit 1
fi

SCRIPT="scripts/check_upstream.py"

# Read the last-checked repo slug from state (if any)
STATE_FILE="$HOME/Library/Application Support/assistant/state/upstream_state.json"
LAST_SLUG=""
if [ -f "$STATE_FILE" ]; then
    LAST_SLUG=$("$PYTHON" -c "
import json, sys
try:
    d = json.load(open('$STATE_FILE'))
    repos = list(d.get('repos', {}).keys())
    print(repos[-1] if repos else '')
except Exception:
    print('')
" 2>/dev/null)
fi

echo "=============================="
echo "  Gap Check"
echo "=============================="
echo ""

if [ -n "$LAST_SLUG" ]; then
    echo "Last checked repo: $LAST_SLUG"
    echo -n "GitHub URL [Enter to re-check $LAST_SLUG]: "
    read -r URL
    if [ -z "$URL" ]; then
        URL="https://github.com/$LAST_SLUG"
    fi
else
    echo -n "GitHub URL: "
    read -r URL
fi

if [ -z "$URL" ]; then
    echo "No URL provided. Exiting."
    echo ""
    echo "Press any key to close..."
    read -rn1
    exit 0
fi

echo ""
echo "Running gap check for: $URL"
echo ""

"$PYTHON" "$SCRIPT" "$URL"

echo ""
echo "=============================="
echo "Done. Copy the output above and paste it into the assistant for gap analysis."
echo ""
echo "Press any key to close..."
read -rn1
