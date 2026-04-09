#!/usr/bin/env bash
# install.sh — one-command installer for ClaudeClaw-assistant
#
# Usage:
#   cd ~/ClaudeClaw/assistant
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
echo -e "${BOLD}  ╔═════════════════════════════════════════════════════════════╗${RESET}"
echo ""
echo -e "${BOLD}     _____ _                 _       _____ _                   ${RESET}"
echo -e "${BOLD}    / ____| |               | |     / ____| |                  ${RESET}"
echo -e "${BOLD}   | |    | | __ _ _   _  __| | ___| |    | | __ ___      __   ${RESET}"
echo -e "${BOLD}   | |    | |/ _\` | | | |/ _\` |/ _ \ |    | |/ _\` \ \ /\ / /  ${RESET}"
echo -e "${BOLD}   | |____| | (_| | |_| | (_| |  __/ |____| | (_| |\ V  V /   ${RESET}"
echo -e "${BOLD}    \_____|_|\__,_|\__,_|\__,_|\___|\_____|_|\__,_| \_/\_/    ${RESET}"
echo ""
echo -e "${BOLD}  ╠═════════════════════════════════════════════════════════════╣${RESET}"
echo -e "${BOLD}           Your AI assistant, locally hosted.                  ${RESET}"
echo -e "${BOLD}  ╚═════════════════════════════════════════════════════════════╝${RESET}"
echo

# ── Helper: find a suitable Python ───────────────────────────────────────────
find_python() {
  PYTHON=""
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" &>/dev/null; then
      version_minor=$("$candidate" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo 0)
      version_major=$("$candidate" -c 'import sys; print(sys.version_info.major)' 2>/dev/null || echo 0)
      if [[ "$version_major" -eq 3 && "$version_minor" -ge "$PYTHON_MIN_MINOR" ]]; then
        PYTHON="$candidate"
        return 0
      fi
    fi
  done
  return 1
}

# ── Step 1: Find Python ──────────────────────────────────────────────────────
step "Step 1 — Checking Python"

if find_python; then
  PYTHON_VERSION=$("$PYTHON" --version 2>&1)
  ok "Found $PYTHON_VERSION ($PYTHON)"
else
  warn "Python 3.${PYTHON_MIN_MINOR}+ not found."
  echo
  echo -n "  Would you like to install it now? [Y/n] "
  read -r INSTALL_PYTHON
  INSTALL_PYTHON="${INSTALL_PYTHON:-Y}"

  if [[ "$INSTALL_PYTHON" =~ ^[Yy] ]]; then
    if [[ "$(uname)" == "Darwin" ]]; then
      # macOS — install via Homebrew
      if ! command -v brew &>/dev/null; then
        echo
        echo "  Homebrew is required to install Python on macOS."
        echo "  Installing Homebrew first..."
        echo
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        # Add Homebrew to PATH for this session
        if [[ -f /opt/homebrew/bin/brew ]]; then
          eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [[ -f /usr/local/bin/brew ]]; then
          eval "$(/usr/local/bin/brew shellenv)"
        fi
      fi
      if command -v brew &>/dev/null; then
        echo "  Installing Python 3.12 via Homebrew..."
        brew install python@3.12
      fi
    else
      # Linux — try apt or dnf
      if command -v apt-get &>/dev/null; then
        echo "  Installing Python 3.12 via apt..."
        sudo apt-get update -qq && sudo apt-get install -y python3.12 python3.12-venv
      elif command -v dnf &>/dev/null; then
        echo "  Installing Python 3.12 via dnf..."
        sudo dnf install -y python3.12
      else
        fail "Could not detect package manager (apt or dnf)."
      fi
    fi

    # Re-check after install
    if find_python; then
      PYTHON_VERSION=$("$PYTHON" --version 2>&1)
      ok "Installed $PYTHON_VERSION ($PYTHON)"
    else
      fail "Python install did not succeed."
      echo
      echo "  Install manually from https://www.python.org/downloads/"
      echo
      exit 1
    fi
  else
    echo
    echo "  Install Python 3.${PYTHON_MIN_MINOR}+ from https://www.python.org/downloads/"
    echo "  or via Homebrew:  brew install python@3.12"
    echo "  Then re-run this installer."
    echo
    exit 1
  fi
fi

# ── Step 2: Check claude CLI ─────────────────────────────────────────────────
step "Step 2 — Checking prerequisites"

if command -v claude &>/dev/null; then
  ok "claude CLI found"
else
  warn "claude CLI not found in PATH"
  echo
  echo -n "  Would you like to install it now? [Y/n] "
  read -r INSTALL_CLAUDE
  INSTALL_CLAUDE="${INSTALL_CLAUDE:-Y}"

  if [[ "$INSTALL_CLAUDE" =~ ^[Yy] ]]; then
    if command -v npm &>/dev/null; then
      echo "  Installing Claude Code via npm..."
      npm install -g @anthropic-ai/claude-code
    elif command -v brew &>/dev/null; then
      echo "  Installing Claude Code via Homebrew..."
      brew install claude
    else
      warn "Could not auto-install (no npm or brew found)."
    fi

    if command -v claude &>/dev/null; then
      ok "claude CLI installed"
    else
      warn "Claude CLI install did not succeed."
      echo "       Install it manually from: https://claude.ai/code"
      echo "       You can install it after setup and before running 'assistant start'."
    fi
  else
    warn "Skipping Claude CLI install."
    echo "       Install it from: https://claude.ai/code"
    echo "       You can install it after setup and before running 'assistant start'."
  fi
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
step "Step 4 — Installing ClaudeClaw"

"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -e "$PROJECT_ROOT"
ok "Installed ClaudeClaw (editable mode)"

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
  echo "# ClaudeClaw" >> "$profile"
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
