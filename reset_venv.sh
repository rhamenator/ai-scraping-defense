#!/bin/bash
#
# SYNOPSIS
#   Completely resets the Python virtual environment.
#
# DESCRIPTION
#   This script automates the process of deleting the old .venv folder,
#   creating a new one, upgrading core packaging tools, and installing
#   all dependencies from requirements.txt.
#
# USAGE
#   ./reset_venv.sh
#

# Use -e to exit immediately if a command fails
set -e

echo "--- Deactivating and removing old virtual environment ---"

# The 'deactivate' command might not be available if the script is run in a non-interactive shell
# or if the venv is not active. We check if it's a declared function first.
if [ "$(type -t deactivate)" = "function" ]; then
  deactivate
fi
rm -rf .venv

echo "--- Creating new virtual environment ---"
# Use python3 to be explicit, as 'python' can sometimes point to Python 2
python3 -m venv .venv

echo "--- Upgrading core packaging tools ---"
# Run the commands using the python executable inside the new venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel

echo "--- Installing project dependencies from requirements.txt ---"
./.venv/bin/python -m pip install -r requirements.txt

echo "---"
echo "Virtual environment reset successfully!"
echo "To activate it, run: source .venv/bin/activate"
