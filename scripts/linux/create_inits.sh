#!/usr/bin/env bash
set -euo pipefail
#
# SYNOPSIS
#   Recursively creates an empty __init__.py file in directories that contain Python scripts.
#
# DESCRIPTION
#   This script ensures Python's test discovery and module importing work reliably
#   by turning directories with Python code into packages. It will only add an
#   __init__.py file to a directory if it finds at least one '.py' file within it.
#
#   It intelligently ignores common directories like .venv, .git, and __pycache__.
#
# USAGE
#   ./create_inits.sh
#

echo "Searching for directories containing Python files..."

# Use an associative array to keep track of which directories need an __init__.py
# This prevents duplicate processing.
declare -A dirs_to_init

# First, find all files ending in .py, excluding specified directories.
# The `-path` option allows for pattern matching on the full path.
# We build up a find command that prunes (ignores) all the excluded directories.
find_args=()
exclude_paths=(./.venv ././.git ./__pycache__ ././.vscode ./node_modules)
for path in "${exclude_paths[@]}"; do
    find_args+=(-path "$path" -prune -o)
done
find_args+=(-type f -name "*.py" -print)

# For each Python file found, get its directory
while IFS= read -r py_file; do
    # Get the directory containing the file
    dir=$(dirname "$py_file")

    # Walk up from the file's directory to the project root
    while [ "$dir" != "." ] && [ "$dir" != "/" ]; do
        # Add the directory to our list if it's not already there
        if [[ -z "${dirs_to_init[$dir]}" ]]; then
            dirs_to_init["$dir"]=1
        fi
        # Move to the parent directory
        dir=$(dirname "$dir")
    done
    # Also add the root directory ('.') to the list
    if [[ -z "${dirs_to_init[.]}" ]]; then
        dirs_to_init["."]=1
    fi
done < <(find . "${find_args[@]}")

# Now, iterate through the unique directories we found
for dir in "${!dirs_to_init[@]}"; do
    INIT_FILE="$dir/__init__.py"
    # Check if the __init__.py file does not already exist
    if [ ! -f "$INIT_FILE" ]; then
        # Create the empty file
        touch "$INIT_FILE"
        echo "Created: $INIT_FILE"
    fi
done

echo "Python __init__.py check complete."
