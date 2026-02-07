#!/usr/bin/env bash
set -euo pipefail

# Determine docker compose command
compose() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo "docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
  else
    echo "ERROR: docker compose/docker-compose not found" >&2
    return 127
  fi
}

# Resolve the defense network name in a robust way
defense_network() {
  # Prefer the network(s) attached to a known service
  for svc in nginx_proxy apache_proxy admin_ui ai_service; do
    if docker ps -a --format '{{.Names}}' | grep -qx "$svc"; then
      local nets
      nets=$(docker inspect "$svc" -f '{{range $k,$v := .NetworkSettings.Networks}}{{println $k}}{{end}}' 2>/dev/null | head -n1)
      if [ -n "${nets:-}" ]; then
        echo "$nets"
        return 0
      fi
    fi
  done
  # Fallback: look for a network whose name ends with _defense_network or equals defense_network
  local name
  name=$(docker network ls --format '{{.Name}}' | grep -E '(^defense_network$|_defense_network$)' | head -n1 || true)
  if [ -n "${name:-}" ]; then
    echo "$name"
    return 0
  fi
  # Last resort: any network containing defense_network
  name=$(docker network ls --format '{{.Name}}' | grep 'defense_network' | head -n1 || true)
  [ -n "${name:-}" ] && echo "$name" || return 1
}

# Wait for a container to become healthy or a port to respond
wait_for_container_healthy() {
  local name="$1" timeout="${2:-60}"
  local start
  start=$(date +%s)
  while :; do
    local status
    status=$(docker inspect -f '{{.State.Health.Status}}' "$name" 2>/dev/null || true)
    [ "$status" = "healthy" ] && return 0
    # If no healthcheck, break and return
    if [ -z "$status" ] || [ "$status" = "<no value>" ]; then
      return 0
    fi
    local now
    now=$(date +%s)
    if [ $((now-start)) -ge "$timeout" ]; then
      echo "Timeout waiting for $name to be healthy" >&2
      return 1
    fi
    sleep 2
  done
}

# Wait for MariaDB inside a container
wait_for_mariadb() {
  local name="$1" timeout="${2:-60}"
  local start
  start=$(date +%s)
  while :; do
    if docker exec "$name" sh -lc "mysqladmin ping -h 127.0.0.1 -uroot -pexample --silent" >/dev/null 2>&1; then
      return 0
    fi
    local now
    now=$(date +%s)
    if [ $((now-start)) -ge "$timeout" ]; then
      echo "Timeout waiting for MariaDB in $name" >&2
      return 1
    fi
    sleep 2
  done
}
