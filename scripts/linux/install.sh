#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

if [ "$(uname -s)" != "Linux" ]; then
  echo "Unsupported OS: $(uname -s). This installer supports Linux only." >&2
  echo "Use scripts/macos/*.zsh on macOS or scripts/windows/*.ps1 on Windows." >&2
  exit 1
fi

# shellcheck source=scripts/linux/lib.sh
source "$SCRIPT_DIR/lib.sh"

PROXY="nginx"
TAKEOVER=false
FORCE_ENV=false
REGENERATE_SECRETS=false
SKIP_VENV_RESET=false
RUN_TESTS=false
SKIP_SMOKE=false

usage() {
  cat <<'USAGE'
Usage: scripts/linux/install.sh [options]

Options:
  --proxy <nginx|apache>  Reverse proxy to expose during install. Default: nginx
  --takeover              Stop host web services and bind the selected proxy to 80/443
  --force-env             Replace .env with sample.env before continuing
  --regenerate-secrets    Recreate local development secrets even if they already exist
  --skip-venv-reset       Skip reset_venv.sh and reuse the existing .venv
  --run-tests             Run test/run_all_tests.py before starting containers
  --skip-smoke            Skip the post-install stack smoke test
  -h, --help              Show this help text
USAGE
}

need_cmd() {
  local cmd="$1" package_hint="${2:-}"
  if command -v "$cmd" >/dev/null 2>&1; then
    return 0
  fi

  echo "Missing required command: $cmd" >&2
  if [ -n "$package_hint" ]; then
    echo "Install it with: sudo apt-get install -y ${package_hint}" >&2
  fi
  exit 1
}

verify_python() {
  if ! python3 - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
  then
    echo "Python 3.10 or newer is required." >&2
    exit 1
  fi

  if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "python3-venv support is required. Install it with: sudo apt-get install -y python3-venv" >&2
    exit 1
  fi
}

verify_prerequisites() {
  need_cmd docker docker.io
  need_cmd git git
  need_cmd python3 python3
  need_cmd curl curl
  need_cmd openssl openssl
  need_cmd awk gawk
  need_cmd sed sed
  need_cmd ss iproute2
  need_cmd htpasswd apache2-utils

  verify_python

  if ! $(docker_ctx) info >/dev/null 2>&1; then
    echo "Docker daemon is not reachable for context '${DOCKER_CONTEXT}'." >&2
    echo "Start Docker Engine and verify it with: docker --context ${DOCKER_CONTEXT} info" >&2
    exit 1
  fi

  if ! compose >/dev/null 2>&1; then
    exit 1
  fi

  if [ "$SKIP_VENV_RESET" = false ] && [ "$(id -u)" -ne 0 ] && ! sudo -n true >/dev/null 2>&1; then
    echo "reset_venv.sh requires root privileges for apt packages." >&2
    echo "Run this installer with sudo or pre-authorize sudo for the session." >&2
    exit 1
  fi
}

ensure_env_file() {
  if [ "$FORCE_ENV" = true ] || [ ! -f .env ]; then
    cp sample.env .env
    chmod 600 .env
    echo "Prepared .env from sample.env"
  fi
}

secrets_initialized() {
  [ -s "$ROOT_DIR/secrets/pg_password.txt" ] &&
    [ -s "$ROOT_DIR/secrets/redis_password.txt" ] &&
    awk -F= '$1=="ADMIN_UI_PASSWORD_HASH" && length($2) > 0 { found=1 } END { exit(found ? 0 : 1) }' .env
}

ensure_secrets() {
  if [ "$REGENERATE_SECRETS" = true ] || ! secrets_initialized; then
    bash "$SCRIPT_DIR/generate_secrets.sh" --update-env
  else
    echo "Reusing existing local secrets. Pass --regenerate-secrets to replace them."
  fi
}

prepare_python_environment() {
  if [ "$SKIP_VENV_RESET" = false ]; then
    if [ "$(id -u)" -eq 0 ]; then
      bash "$SCRIPT_DIR/reset_venv.sh"
    else
      sudo bash "$SCRIPT_DIR/reset_venv.sh"
    fi
  elif [ ! -x "$ROOT_DIR/.venv/bin/python" ]; then
    echo "No usable .venv found. Re-run without --skip-venv-reset." >&2
    exit 1
  fi

  "$ROOT_DIR/.venv/bin/pip" install -r requirements.txt -c constraints.txt
  "$ROOT_DIR/.venv/bin/python" scripts/validate_env.py

  if [ "$RUN_TESTS" = true ]; then
    "$ROOT_DIR/.venv/bin/python" test/run_all_tests.py
  fi
}

launch_stack() {
  if [ "$TAKEOVER" = true ]; then
    bash "$SCRIPT_DIR/quick_takeover.sh" "$PROXY"
  else
    bash "$SCRIPT_DIR/quick_proxy.sh" "$PROXY"
  fi
}

main() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --proxy)
        PROXY="${2:-}"
        shift 2
        ;;
      --takeover)
        TAKEOVER=true
        shift
        ;;
      --force-env)
        FORCE_ENV=true
        shift
        ;;
      --regenerate-secrets)
        REGENERATE_SECRETS=true
        shift
        ;;
      --skip-venv-reset)
        SKIP_VENV_RESET=true
        shift
        ;;
      --run-tests)
        RUN_TESTS=true
        shift
        ;;
      --skip-smoke)
        SKIP_SMOKE=true
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

  case "$PROXY" in
    nginx|apache) ;;
    *)
      echo "Unsupported proxy: ${PROXY}" >&2
      usage
      exit 2
      ;;
  esac

  echo "=== AI Scraping Defense: Linux Installer ==="
  verify_prerequisites
  ensure_env_file
  bash "$SCRIPT_DIR/setup_local_dirs.sh"
  ensure_secrets
  prepare_python_environment
  ensure_no_new_privileges_env
  launch_stack

  if [ "$SKIP_SMOKE" = false ]; then
    bash "$SCRIPT_DIR/stack_smoke_test.sh" --proxy "$PROXY"
  fi

  echo ""
  echo "Install complete."
  echo "Proxy mode: ${PROXY}"
  if [ "$TAKEOVER" = true ]; then
    echo "Takeover mode is active. Roll back host web services with:"
    echo "  scripts/linux/reset_web_server.sh restore-latest"
  fi
  echo "Uninstall the stack with:"
  echo "  scripts/linux/uninstall.sh"
}

main "$@"
