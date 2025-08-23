#!/bin/zsh
# Completely resets the Python virtual environment for macOS users.
# Mirrors reset_venv.sh but installs dependencies with Homebrew.

set -e

echo "--- Step 1: Installing required system dependencies ---"
if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew not found. Visit https://brew.sh to install." >&2
  exit 1
fi
brew update
brew install libxml2 libxslt

echo -e "\n--- Step 2: Deactivating and removing old virtual environment ---"
if typeset -f deactivate >/dev/null; then
  deactivate
fi
rm -rf .venv

echo -e "\n--- Step 3: Creating new virtual environment ---"
python3 -m venv .venv

echo -e "\n--- Step 4: Upgrading core packaging tools ---"
./.venv/bin/python -m pip install --upgrade pip setuptools wheel

echo -e "\n--- Step 5: Installing project dependencies from requirements.txt ---"
./.venv/bin/python -m pip install -r requirements.txt

echo -e "\n---"
echo "Virtual environment reset successfully!"
echo "To activate it, run: source .venv/bin/activate"
