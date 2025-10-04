#!/usr/bin/env bash
# =============================================================================
#  post_takeover_wordpress.sh - attach WordPress after quick_takeover
#
#  Assumes quick_takeover.sh has already launched the AI Scraping Defense stack
#  on the defense_network. This script updates REAL_BACKEND_HOST and starts
#  WordPress and MariaDB containers on that network.
# =============================================================================
set -euo pipefail

# Update REAL_BACKEND_HOST to point at the WordPress container
if grep -q '^REAL_BACKEND_HOST=' .env; then
  sed -i.bak 's|^REAL_BACKEND_HOST=.*|REAL_BACKEND_HOST=http://wordpress:80|' .env && rm -f .env.bak
else
  echo 'REAL_BACKEND_HOST=http://wordpress:80' >> .env
fi

# Determine the Docker network created by quick_takeover
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
NETWORK_NAME=$(defense_network || echo "")
if [ -z "$NETWORK_NAME" ]; then
  echo "Could not locate the defense_network. Did quick_takeover run?"
  exit 1
fi

# Launch MariaDB for WordPress
if [ ! "$(docker ps -q -f name=wordpress_db)" ]; then
  docker run -d --name wordpress_db \
    --network "$NETWORK_NAME" \
    -e MYSQL_ROOT_PASSWORD=example \
    -e MYSQL_DATABASE=wordpress \
    -e MYSQL_USER=wordpress \
    -e MYSQL_PASSWORD=wordpress \
    mariadb:10
else
  echo "wordpress_db container already running"
fi

# Launch the WordPress container
if [ ! "$(docker ps -q -f name=wordpress)" ]; then
  echo "Waiting for MariaDB to be ready..."
  wait_for_mariadb wordpress_db 120 || true
  docker run -d --name wordpress \
    --network "$NETWORK_NAME" \
    -p 8082:80 \
    -e WORDPRESS_DB_HOST=wordpress_db:3306 \
    -e WORDPRESS_DB_USER=wordpress \
    -e WORDPRESS_DB_PASSWORD=wordpress \
    -e WORDPRESS_DB_NAME=wordpress \
    wordpress:php8.1-apache
else
  echo "wordpress container already running"
fi

echo "WordPress available at http://localhost:8082"
echo "Proxy via AI Scraping Defense at http://localhost:8080"
