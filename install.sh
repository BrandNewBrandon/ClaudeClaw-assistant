#!/usr/bin/env bash
# install.sh — one-command installer for assistant-runtime
#
# Usage:
#   cd ~/Projects/assistant-runtime
#   bash install.sh
#
# What it does:
#   1. Checks Python 3.11+
#   2. Creates .venv if it doesn't exist
#   3. Installs the package in editable mode
#   4. Adds .venv/bin to PATH in ~/.zshrc / ~/.bash_profile (once)
#   5. Runs 'assistant init' to complete setup
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$PROJECT_ROOT/.venv"
PYTHON_MIN_MINOR=11

# ── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; RESET='\033[0m'
ok()   { echo -e "  ${GREEN}✓${RESET} $*"; }
warn() { echo -e "  ${YELLOW}!${RESET} $*"; }
fail() { echo -e "  ${RED}✗${RESET} $*"; }
step() { echo -e "\n${BOLD}$*${RESET}"; }

echo
echo -e "${BOLD}╔══════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║      assistant-runtime  ·  Installer             ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════════════╝${RESET}"
echo

# ── Step 1: Find Python ──────────────────────────────────────────────────────
step "Step 1 — Checking Python"

PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" &>/dev/null; then
    version_minor=$("$candidate" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo 0)
    version_major=$("$candidate" -c 'import sys; print(sys.version_info.major)' 2>/dev/null || echo 0)
    if [[ "$version_major" -eq 3 && "$version_minor" -ge "$PYTHON_MIN_MINOR" ]]; then
      PYTHON="$candidate"
      break
    fi
  fi
done

if [[ -z "$PYTHON" ]]; then
  fail "Python 3.${PYTHON_MIN_MINOR}+ not found."
  echo
  echo "  Install it from https://www.python.org/downloads/"
  echo "  or via Homebrew:  brew install python@3.12"
  echo
  exit 1
fi

PYTHON_VERSION=$("$PYTHON" --version 2>&1)
ok "Found $PYTHON_VERSION ($PYTHON)"

# ── Step 2: Check claude CLI ─────────────────────────────────────────────────
step "Step 2 — Checking prerequisites"

if command -v claude &>/dev/null; then
  ok "claude CLI found"
else
  warn "claude CLI not found in PATH"
  echo "       Install it from: https://claude.ai/code"
  echo "       You can install it after setup and before running 'assistant start'."
fi

# ── Step 3: Create venv ──────────────────────────────────────────────────────
step "Step 3 — Setting up virtual environment"

if [[ -d "$VENV" && -f "$VENV/bin/python" ]]; then
  ok "Virtual environment already exists at $VENV"
else
  echo "  Creating .venv..."
  "$PYTHON" -m venv "$VENV"
  ok "Created .venv"
fi

# ── Step 4: Install package ──────────────────────────────────────────────────
step "Step 4 — Installing assistant-runtime"

"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -e "$PROJECT_ROOT"
ok "Installed assistant-runtime (editable mode)"

# ── Step 5: Add to PATH ──────────────────────────────────────────────────────
step "Step 5 — Adding 'assistant' to PATH"

VENV_BIN="$VENV/bin"
PATH_LINE="export PATH=\"$VENV_BIN:\$PATH\""

# Detect which shell profile to use
add_to_profile() {
  local profile="$1"
  if [[ -f "$profile" ]] && grep -qF "$VENV_BIN" "$profile" 2>/dev/null; then
    ok "PATH already set in $profile — skipping"
    return 0
  fi
  echo "" >> "$profile"
  echo "# assistant-runtime" >> "$profile"
  echo "$PATH_LINE" >> "$profile"
  ok "Added PATH entry to $profile"
  return 0
}

PROFILE_UPDATED=""
if [[ "${SHELL:-}" == */zsh ]]; then
  add_to_profile "$HOME/.zshrc"
  PROFILE_UPDATED="$HOME/.zshrc"
elif [[ "${SHELL:-}" == */bash ]]; then
  # On macOS bash uses .bash_profile for login shells
  if [[ "$(uname)" == "Darwin" ]]; then
    add_to_profile "$HOME/.bash_profile"
    PROFILE_UPDATED="$HOME/.bash_profile"
  else
    add_to_profile "$HOME/.bashrc"
    PROFILE_UPDATED="$HOME/.bashrc"
  fi
else
  warn "Unknown shell ($SHELL). Add the following to your shell profile manually:"
  echo "       $PATH_LINE"
fi

# Also export for the current session so 'assistant init' works immediately
export PATH="$VENV_BIN:$PATH"

# ── Step 6: Verify ───────────────────────────────────────────────────────────
step "Step 6 — Verifying install"

if command -v assistant &>/dev/null; then
  ASSISTANT_PATH=$(command -v assistant)
  ok "assistant command available at $ASSISTANT_PATH"
else
  warn "Could not find 'assistant' in PATH for this session — using full path."
  ASSISTANT_PATH="$VENV_BIN/assistant"
fi

# ── Step 7: Run init ─────────────────────────────────────────────────────────
step "Step 7 — First-time setup"
echo

echo "  Installation complete! Launching setup wizard..."
echo
sleep 0.5

"$ASSISTANT_PATH" init

# ── Done ─────────────────────────────────────────────────────────────────────
echo
echo -e "${BOLD}  Installation complete.${RESET}"
echo
if [[ -n "$PROFILE_UPDATED" ]]; then
  echo "  To use 'assistant' in new terminals, your profile was updated."
  echo "  It will take effect automatically in every new terminal window."
  echo
  echo "  To use it in this terminal right now:"
  echo "    source $PROFILE_UPDATED"
fi
echo
