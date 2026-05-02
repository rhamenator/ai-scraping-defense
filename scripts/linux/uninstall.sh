#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

if [ "$(uname -s)" != "Linux" ]; then
  echo "Unsupported OS: $(uname -s). This uninstall helper supports Linux only." >&2
  exit 1
fi

# shellcheck source=scripts/linux/lib.sh
source "$SCRIPT_DIR/lib.sh"

PURGE_DATA=false
REMOVE_IMAGES=false
RESTORE_WEBSERVER=""

usage() {
  cat <<'USAGE'
Usage: scripts/linux/uninstall.sh [options]

Options:
  --purge-data                 Remove Docker volumes as part of compose down
  --remove-images              Remove locally built project images after shutdown
  --restore-webserver latest   Restore the newest host webserver snapshot
  --restore-webserver <path>   Restore a specific webserver snapshot
  -h, --help                   Show this help text
USAGE
}

main() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --purge-data)
        PURGE_DATA=true
        shift
        ;;
      --remove-images)
        REMOVE_IMAGES=true
        shift
        ;;
      --restore-webserver)
        RESTORE_WEBSERVER="${2:-}"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        echo "Unknown argument: $1" >&2
        usage
        exit 2
        ;;
    esac
  done

  down_args=(down --remove-orphans)
  if [ "$PURGE_DATA" = true ]; then
    down_args+=(--volumes)
  fi
  $(compose) "${down_args[@]}"

  if [ "$REMOVE_IMAGES" = true ]; then
    $(docker_ctx) image rm ai-scraping-defense-ai_service ai-scraping-defense-admin_ui ai-scraping-defense-escalation_engine ai-scraping-defense-tarpit_api >/dev/null 2>&1 || true
  fi

  if [ -n "$RESTORE_WEBSERVER" ]; then
    if [ "$RESTORE_WEBSERVER" = "latest" ]; then
      bash "$SCRIPT_DIR/reset_web_server.sh" restore-latest
    else
      bash "$SCRIPT_DIR/reset_web_server.sh" restore "$RESTORE_WEBSERVER"
    fi
  fi

  echo "Linux uninstall complete."
}

main "$@"
