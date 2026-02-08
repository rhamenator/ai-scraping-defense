#!/usr/bin/env bash
set -euo pipefail

# Snapshot host web server configuration (Apache/nginx) so you can revert after a takeover test.
#
# Creates a timestamped snapshot under ./backups/webserver/.
# Requires sudo to read /etc and query service state.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT_DIR"

TS="$(date -u +%Y%m%d-%H%M%S)"
OUT_DIR="$ROOT_DIR/backups/webserver/$TS"
mkdir -p "$OUT_DIR"

echo "Writing snapshot to: $OUT_DIR"

{
  echo "timestamp_utc=$TS"
  echo "hostname=$(hostname)"
  echo "kernel=$(uname -r)"
} > "$OUT_DIR/host.txt"

if command -v systemctl >/dev/null 2>&1; then
  {
    echo "apache2=$(systemctl is-active apache2 2>/dev/null || true)"
    echo "nginx=$(systemctl is-active nginx 2>/dev/null || true)"
  } > "$OUT_DIR/services.txt"
fi

if command -v apache2ctl >/dev/null 2>&1; then
  sudo apache2ctl -V > "$OUT_DIR/apache2ctl_V.txt" 2>&1 || true
  sudo apache2ctl -M > "$OUT_DIR/apache2ctl_M.txt" 2>&1 || true
fi

if command -v nginx >/dev/null 2>&1; then
  sudo nginx -V > "$OUT_DIR/nginx_V.txt" 2>&1 || true
  sudo nginx -T > "$OUT_DIR/nginx_T.txt" 2>&1 || true
fi

if [ -d /etc/apache2 ]; then
  sudo tar -C / -czf "$OUT_DIR/etc-apache2.tgz" etc/apache2
fi
if [ -d /etc/nginx ]; then
  sudo tar -C / -czf "$OUT_DIR/etc-nginx.tgz" etc/nginx
fi

echo "Done."
