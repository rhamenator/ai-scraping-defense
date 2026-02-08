#!/usr/bin/env bash
set -euo pipefail

# Restore host web server configuration (Apache/nginx) from a snapshot created by webserver_snapshot.sh
#
# Usage:
#   scripts/linux/webserver_restore.sh backups/webserver/<timestamp>
#
# Requires sudo.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

SNAPSHOT_DIR="${1:-}"
if [ -z "$SNAPSHOT_DIR" ]; then
  echo "Usage: $0 backups/webserver/<timestamp>" >&2
  exit 2
fi

if [ ! -d "$SNAPSHOT_DIR" ]; then
  echo "Snapshot directory not found: $SNAPSHOT_DIR" >&2
  exit 2
fi

echo "Restoring from: $SNAPSHOT_DIR"

if [ "$(id -u)" -ne 0 ]; then
  echo "This script must be run with sudo (it restores into /etc and restarts services)." >&2
  exit 1
fi

if command -v systemctl >/dev/null 2>&1; then
  sudo systemctl stop apache2 >/dev/null 2>&1 || true
  sudo systemctl stop nginx >/dev/null 2>&1 || true
fi

if [ -f "$SNAPSHOT_DIR/etc-apache2.tgz" ]; then
  sudo tar -C / -xzf "$SNAPSHOT_DIR/etc-apache2.tgz"
fi

if [ -f "$SNAPSHOT_DIR/etc-nginx.tgz" ]; then
  sudo tar -C / -xzf "$SNAPSHOT_DIR/etc-nginx.tgz"
fi

if command -v systemctl >/dev/null 2>&1; then
  if [ -f "$SNAPSHOT_DIR/services.txt" ]; then
    apache2_state=$(rg -n "^apache2=" "$SNAPSHOT_DIR/services.txt" -o -N | sed 's/^apache2=//' || true)
    nginx_state=$(rg -n "^nginx=" "$SNAPSHOT_DIR/services.txt" -o -N | sed 's/^nginx=//' || true)
    if [ "$apache2_state" = "active" ]; then
      sudo systemctl start apache2 || true
    fi
    if [ "$nginx_state" = "active" ]; then
      sudo systemctl start nginx || true
    fi
  else
    sudo systemctl start apache2 >/dev/null 2>&1 || true
    sudo systemctl start nginx >/dev/null 2>&1 || true
  fi
fi

echo "Restore complete."
