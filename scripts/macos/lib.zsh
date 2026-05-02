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
