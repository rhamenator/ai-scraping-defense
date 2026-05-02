#!/usr/bin/env zsh
set -e
set -u
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

exec "$SCRIPT_DIR/install.zsh" --run-tests "$@"
