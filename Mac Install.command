#!/usr/bin/env bash
# Mac Install.command — double-click this file in Finder to install ClaudeClaw.
# macOS will open it in Terminal automatically.

# Move to the project root (where this file lives)
cd "$(dirname "$0")" || { echo "Could not find project root."; read -rn1; exit 1; }

bash install.sh

echo ""
echo "Press any key to close this window..."
read -rn1
