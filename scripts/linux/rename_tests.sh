#!/usr/bin/env bash
set -euo pipefail
#
# SYNOPSIS
#   Recursively finds and renames Python test files to the standard unittest format.
#
# DESCRIPTION
#   This script searches the 'test' directory and its subdirectories for any
#   files ending in '.test.py' and renames them to the 'test_*.py' convention.
#   For example, 'admin_ui.test.py' becomes 'test_admin_ui.py'.
#
#   This is necessary for Python's built-in unittest discovery to find and run the tests.
#
# USAGE
#   ./rename_tests.sh
#

# Find all files within the 'test' directory that match the old naming pattern
# The -print0 and "while read -d ''" handles filenames with spaces or special characters
find ./test -type f -name "*.test.py" -print0 | while IFS= read -r -d '' old_path; do
    # Get the directory of the file (e.g., ./test/admin_ui)
    dir=$(dirname "$old_path")
    # Get just the filename (e.g., admin_ui.test.py)
    filename=$(basename "$old_path")
    
    # Remove the '.test.py' suffix to get the base module name (e.g., admin_ui)
    module_name=${filename%.test.py}
    
    # Prepend 'test_' and add back the .py extension (e.g., test_admin_ui.py)
    new_filename="test_${module_name}.py"
    
    # Construct the full new path
    new_path="$dir/$new_filename"
    
    # Rename the file
    mv "$old_path" "$new_path"
    
    echo "Renamed: $old_path -> $new_path"
done

echo
echo "File renaming process complete."
