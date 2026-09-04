#!/bin/bash

# Script to run uv sync in directories containing pyproject.toml
# Excludes all hidden directories (folders starting with .)

set -euo pipefail  # Exit on error, undefined vars, pipe failures

SEARCH_DIR="${1:-.}"

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed or not in PATH" >&2
    exit 1
fi

# Function to process a directory
process_directory() {
    local dir="$1"
    
    echo "Processing: $dir"
    
    # Change to directory and run uv sync
    if cd "$dir" 2>/dev/null; then
        if uv sync; then
            echo "✓ Success: $dir"
            cd - > /dev/null  # Return to original directory
            return 0
        else
            echo "✗ Failed: $dir"
            cd - > /dev/null  # Return to original directory
            return 1
        fi
    else
        echo "✗ Cannot access directory: $dir"
        return 1
    fi
}

# Main execution
echo "Searching for pyproject.toml files in '$SEARCH_DIR' (excluding hidden directories)..."

# Find all pyproject.toml files, excluding any directory starting with .
find "$SEARCH_DIR" -name "pyproject.toml" -type f -not -path "*/.*/*" | while read -r file; do
    if [ -n "$file" ] && [ -f "$file" ]; then
        dir=$(dirname "$file")
        process_directory "$dir"
    fi
done

echo "Done."
