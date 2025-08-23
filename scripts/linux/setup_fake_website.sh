#!/bin/bash
# =============================================================================
#  setup_fake_website.sh - launch a simple test web server
#
#  This helper creates a small Nginx container serving a fake website and
#  connects it to the AI Scraping Defense stack by setting REAL_BACKEND_HOST.
#
#  DISCLAIMER: This script is meant for local testing only. Use it at your own
#  risk and do not expose the stack to production traffic without review.
#
#  Recommended resources for running the full stack and test site on one machine:
#    * 4 CPU cores
#    * 8 GB RAM
#    * 10+ GB of free disk space
# =============================================================================
set -e

# Ensure .env exists
if [ ! -f .env ]; then
  cp sample.env .env
  echo "Created .env from sample.env"
fi

# Add or update REAL_BACKEND_HOST in .env
if grep -q '^REAL_BACKEND_HOST=' .env; then
  sed -i.bak 's|^REAL_BACKEND_HOST=.*|REAL_BACKEND_HOST=http://fake_website:80|' .env && rm -f .env.bak
else
  echo 'REAL_BACKEND_HOST=http://fake_website:80' >> .env
fi

# Create a minimal website if not already present
mkdir -p fake_site
if [ ! -f fake_site/index.html ]; then
cat > fake_site/index.html <<'HTML'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Fake Website</title>
</head>
<body>
  <h1>Hello from the Fake Website!</h1>
  <p>If you see this page through the proxy, the stack is working.</p>
</body>
</html>
HTML
fi

# Start the AI Scraping Defense stack
docker-compose up --build -d

# Determine the Docker network created by docker-compose
NETWORK_NAME=$(docker network ls --filter name=defense_network -q | head -n 1)
if [ -z "$NETWORK_NAME" ]; then
  echo "Could not locate the defense_network. Is the stack running?"
  exit 1
fi

# Launch the fake website container
if [ ! "$(docker ps -q -f name=fake_website)" ]; then
  docker run -d --name fake_website \
    --network $NETWORK_NAME \
    -p 8081:80 \
    -v $(pwd)/fake_site:/usr/share/nginx/html:ro \
    nginx:alpine
else
  echo "fake_website container already running"
fi

echo "Fake site available at http://localhost:8081"
echo "Proxy via AI Scraping Defense at http://localhost:8080"
