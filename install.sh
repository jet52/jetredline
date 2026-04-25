#!/usr/bin/env bash
set -euo pipefail

SKILL_NAME="jetredline"
INSTALL_DIR="$HOME/.claude/skills/$SKILL_NAME"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing $SKILL_NAME skill..."

# Create target directory
mkdir -p "$INSTALL_DIR"

# Copy skill files
cp -a "$SCRIPT_DIR/skills/jetredline/"* "$INSTALL_DIR/"

echo "Installed to $INSTALL_DIR"

# --- Python virtual environment ---
echo ""
echo "Setting up Python virtual environment..."

VENV_DIR="$INSTALL_DIR/.venv"

if command -v uv &>/dev/null; then
    echo "Using uv to create venv..."
    uv venv "$VENV_DIR" --clear
    uv pip install -r "$INSTALL_DIR/requirements.txt" --python "$VENV_DIR/bin/python"
elif command -v python3 &>/dev/null; then
    echo "Using python3 to create venv..."
    python3 -m venv "$VENV_DIR" --clear
    "$VENV_DIR/bin/pip" install --upgrade pip
    "$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
else
    echo "ERROR: Neither uv nor python3 found. Cannot create virtual environment."
    echo "  Install Python 3 from https://www.python.org/ or uv from https://docs.astral.sh/uv/"
    exit 1
fi

echo "Python packages installed."

# --- Node.js dependencies ---
echo ""
echo "Installing Node.js dependencies..."

if command -v npm &>/dev/null; then
    cd "$INSTALL_DIR" && npm install
    echo "Node packages installed."
else
    echo "ERROR: npm not found. Cannot install Node.js dependencies."
    echo "  Install Node.js from https://nodejs.org/"
    exit 1
fi

echo ""
echo "Done."
