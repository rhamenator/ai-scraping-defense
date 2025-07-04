#!/bin/bash
#
# SYNOPSIS
#   Completely resets the Python virtual environment.
#
# DESCRIPTION
#   This script first ensures that system-level dependencies required for
#   building Python packages are installed. It then automates the process of
#   deleting the old .venv folder, creating a new one, upgrading core
#   packaging tools, and installing all dependencies from requirements.txt.
#
# USAGE
#   sudo ./reset_venv.sh
#

# Use -e to exit immediately if a command fails
set -e

echo "--- Step 1: Installing required system dependencies ---"
# The lxml package requires these development libraries to build correctly.
# This command will run 'apt update' and then install the packages.
# The 'sudo' is assumed if you run the script with it, as recommended.
apt-get update && apt-get install -y libxml2-dev libxslt1-dev

echo -e "\n--- Step 2: Deactivating and removing old virtual environment ---"

# The 'deactivate' command might not be available if the script is run in a non-interactive shell
# or if the venv is not active. We check if it's a declared function first.
if [ "$(type -t deactivate)" = "function" ]; then
  deactivate
fi
rm -rf .venv

echo -e "\n--- Step 3: Creating new virtual environment ---"
# Use python3 to be explicit, as 'python' can sometimes point to Python 2
python3 -m venv .venv

echo -e "\n--- Step 4: Upgrading core packaging tools ---"
# Run the commands using the python executable inside the new venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel

echo -e "\n--- Step 5: Installing project dependencies from requirements.txt ---"
./.venv/bin/python -m pip install -r requirements.txt

echo -e "\n---"
echo "Virtual environment reset successfully!"
echo "To activate it, run: source .venv/bin/activate"

