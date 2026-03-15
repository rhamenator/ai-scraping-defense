#!/usr/bin/env zsh
set -e
set -u
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

source "$SCRIPT_DIR/lib.zsh"

PURGE_DATA=false
REMOVE_IMAGES=false

usage() {
  cat <<'USAGE'
Usage: scripts/macos/uninstall.zsh [options]

Options:
  --purge-data    Remove Docker volumes as part of compose down
  --remove-images Remove locally built project images after shutdown
  -h, --help      Show this help text
USAGE
}

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
if [[ "$PURGE_DATA" == true ]]; then
  down_args+=(--volumes)
fi

$(compose) "${down_args[@]}"

if [[ "$REMOVE_IMAGES" == true ]]; then
  docker image rm ai-scraping-defense-ai_service ai-scraping-defense-admin_ui ai-scraping-defense-escalation_engine ai-scraping-defense-tarpit_api >/dev/null 2>&1 || true
fi

echo "macOS uninstall complete."
