#!/usr/bin/env bash
set -euo pipefail

# Convenience wrapper around webserver snapshot/restore scripts.
#
# Usage:
#   scripts/linux/reset_web_server.sh snapshot
#   scripts/linux/reset_web_server.sh restore backups/webserver/<timestamp>
#   scripts/linux/reset_web_server.sh restore-latest

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'USAGE'
Usage:
  scripts/linux/reset_web_server.sh snapshot
  scripts/linux/reset_web_server.sh restore <snapshot_dir>
  scripts/linux/reset_web_server.sh restore-latest

Commands:
  snapshot        Capture current host Apache/nginx state and config backups.
  restore         Restore from a specific snapshot directory.
  restore-latest  Restore from the newest snapshot in backups/webserver/.
USAGE
}

latest_snapshot() {
  ls -1dt "$ROOT_DIR"/backups/webserver/* 2>/dev/null | head -n1
}

cmd="${1:-snapshot}"

case "$cmd" in
  snapshot)
    bash "$SCRIPT_DIR/webserver_snapshot.sh"
    ;;
  restore)
    snapshot_dir="${2:-}"
    if [ -z "$snapshot_dir" ]; then
      echo "Missing snapshot directory for restore." >&2
      usage
      exit 2
    fi
    sudo bash "$SCRIPT_DIR/webserver_restore.sh" "$snapshot_dir"
    ;;
  restore-latest)
    snapshot_dir="$(latest_snapshot)"
    if [ -z "$snapshot_dir" ]; then
      echo "No snapshots found under backups/webserver/." >&2
      exit 2
    fi
    echo "Restoring latest snapshot: $snapshot_dir"
    sudo bash "$SCRIPT_DIR/webserver_restore.sh" "$snapshot_dir"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage
    exit 2
    ;;
esac
