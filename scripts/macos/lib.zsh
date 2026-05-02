#!/usr/bin/env zsh
set -e
set -u
set -o pipefail

compose() {
  if command -v docker >/dev/null 2>&1; then
    if docker compose version >/dev/null 2>&1; then
      echo "docker compose"
      return
    fi
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
    return
  fi
  echo "docker compose"
}

supports_no_new_privileges() {
  docker run --rm --security-opt no-new-privileges:true alpine:3.20 true >/dev/null 2>&1
}

ensure_no_new_privileges_env() {
  if [[ -n "${NO_NEW_PRIVILEGES:-}" ]]; then
    return 0
  fi

  if supports_no_new_privileges; then
    export NO_NEW_PRIVILEGES=true
  else
    export NO_NEW_PRIVILEGES=false
    echo "Runtime does not support no-new-privileges:true; setting NO_NEW_PRIVILEGES=false."
  fi
}

env_file_value() {
  local key="$1"
  local file="${2:-.env}"
  awk -F= -v k="$key" '$1==k { print substr($0, index($0, "=") + 1); exit }' "$file"
}

port_in_use() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

nginx_owns_host_port() {
  local port="$1"
  local container_port="$2"
  local mapped_ports

  mapped_ports=$(docker ps --filter name=^/nginx_proxy$ --format '{{.Ports}}' 2>/dev/null || true)
  echo "$mapped_ports" | grep -Eq "(^|, )[^,]*:${port}->${container_port}/tcp"
}

defense_network() {
  local svc nets
  for svc in nginx_proxy apache_proxy admin_ui ai_service; do
    if docker ps -a --format '{{.Names}}' | grep -qx "$svc"; then
      nets=$(docker inspect "$svc" -f '{{range $k,$v := .NetworkSettings.Networks}}{{println $k}}{{end}}' 2>/dev/null | head -n1)
      if [ -n "$nets" ]; then
        echo "$nets"; return 0
      fi
    fi
  done
  docker network ls --format '{{.Name}}' | grep -E '(^defense_network$|_defense_network$)' | head -n1
}
