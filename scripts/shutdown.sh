#!/bin/bash
# Gracefully stop all services started via docker-compose
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."
if [ -f docker-compose.yaml ]; then
    echo "Stopping containers..."
    docker-compose down
else
    echo "docker-compose.yaml not found" >&2
    exit 1
fi
