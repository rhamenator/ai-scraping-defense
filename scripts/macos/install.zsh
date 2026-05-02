#!/usr/bin/env zsh
set -e
set -u
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

source "$SCRIPT_DIR/lib.zsh"

PROXY="nginx"
TAKEOVER=false
FORCE_ENV=false
REGENERATE_SECRETS=false
SKIP_VENV_RESET=false
RUN_TESTS=false
SKIP_SMOKE=false

usage() {
  cat <<'USAGE'
Usage: scripts/macos/install.zsh [options]

Options:
  --proxy <nginx|apache>  Reverse proxy to expose during install. Default: nginx
  --takeover              Stop host web services and bind the selected proxy to 80/443
  --force-env             Replace .env with sample.env before continuing
  --regenerate-secrets    Recreate local development secrets even if they already exist
  --skip-venv-reset       Skip reset_venv.zsh and reuse the existing .venv
  --run-tests             Run test/run_all_tests.py before starting containers
  --skip-smoke            Skip the post-install stack smoke test
  -h, --help              Show this help text
USAGE
}

need_cmd() {
  local cmd="$1"
  local hint="$2"
  if command -v "$cmd" >/dev/null 2>&1; then
    return 0
  fi
  echo "Missing required command: $cmd" >&2
  if [[ -n "$hint" ]]; then
    echo "$hint" >&2
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
}

secrets_initialized() {
  [[ -s "$ROOT_DIR/secrets/pg_password.txt" ]] &&
    [[ -s "$ROOT_DIR/secrets/redis_password.txt" ]] &&
    [[ -n "$(env_file_value ADMIN_UI_PASSWORD_HASH .env)" ]]
}

verify_prerequisites() {
  need_cmd docker "Install Docker Desktop and start it before rerunning the installer."
  need_cmd python3 "Install Python with Homebrew: brew install python"
  need_cmd curl "Install curl via Xcode tools or Homebrew."
  need_cmd openssl "Install OpenSSL with Homebrew: brew install openssl"
  need_cmd htpasswd "Install apache2-utils via Homebrew: brew install httpd"
  need_cmd lsof "Install Xcode command line tools if lsof is unavailable."
  verify_python

  if ! docker info >/dev/null 2>&1; then
    echo "Docker Desktop is not reachable. Start Docker Desktop and verify docker info succeeds." >&2
    exit 1
  fi

  if ! $(compose) version >/dev/null 2>&1; then
    echo "docker compose is required." >&2
    exit 1
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

  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "Unsupported OS: $(uname -s). This installer supports macOS only." >&2
    echo "Use scripts/linux/*.sh on Linux or scripts/windows/*.ps1 on Windows." >&2
    exit 1
  fi

  echo "=== AI Scraping Defense: macOS Installer ==="
  verify_prerequisites

  if [[ "$FORCE_ENV" == true || ! -f .env ]]; then
    cp sample.env .env
    chmod 600 .env
    echo "Prepared .env from sample.env"
  fi

  "$SCRIPT_DIR/setup_local_dirs.zsh"

  if [[ "$REGENERATE_SECRETS" == true ]] || ! secrets_initialized; then
    "$SCRIPT_DIR/generate_secrets.zsh" --update-env
  else
    echo "Reusing existing local secrets. Pass --regenerate-secrets to replace them."
  fi
  chmod 600 .env

  if [[ "$SKIP_VENV_RESET" == false ]]; then
    "$SCRIPT_DIR/reset_venv.zsh"
  elif [[ ! -x "$ROOT_DIR/.venv/bin/python" ]]; then
    echo "No usable .venv found. Re-run without --skip-venv-reset." >&2
    exit 1
  fi

  ./.venv/bin/pip install -r requirements.txt -c constraints.txt
  ./.venv/bin/python scripts/validate_env.py

  if [[ "$RUN_TESTS" == true ]]; then
    ./.venv/bin/python test/run_all_tests.py
  fi

  ensure_no_new_privileges_env

  if [[ "$TAKEOVER" == true ]]; then
    "$SCRIPT_DIR/quick_takeover.zsh" "$PROXY"
  else
    "$SCRIPT_DIR/quick_proxy.zsh" "$PROXY"
  fi

  if [[ "$SKIP_SMOKE" == false ]]; then
    "$SCRIPT_DIR/stack_smoke_test.zsh" --proxy "$PROXY"
  fi

  echo ""
  echo "Install complete."
  echo "Proxy mode: ${PROXY}"
  echo "Uninstall the stack with:"
  echo "  ./scripts/macos/uninstall.zsh"
}

main "$@"
