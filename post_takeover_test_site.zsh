#!/bin/zsh
# =============================================================================
#  post_takeover_test_site.zsh - attach simple test site after quick_takeover
#
#  Assumes quick_takeover.zsh has already launched the AI Scraping Defense stack
#  on the defense_network. This script updates REAL_BACKEND_HOST and starts
#  a minimal Nginx server on that network.
# =============================================================================
set -e

# Update REAL_BACKEND_HOST to point at the fake_website container
if grep -q '^REAL_BACKEND_HOST=' .env; then
  sed -i.bak 's|^REAL_BACKEND_HOST=.*|REAL_BACKEND_HOST=http://fake_website:80|' .env && rm -f .env.bak
else
  echo 'REAL_BACKEND_HOST=http://fake_website:80' >> .env
fi

# Determine the Docker network created by quick_takeover
NETWORK_NAME=$(docker network ls --filter name=defense_network -q | head -n 1)
if [ -z "$NETWORK_NAME" ]; then
  echo "Could not locate the defense_network. Did quick_takeover run?"
  exit 1
fi

# Create a simple test page
mkdir -p test_site
if [ ! -f test_site/index.html ]; then
cat > test_site/index.html <<'HTML'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Test Site</title>
</head>
<body>
  <h1>Hello from the Test Site!</h1>
  <p>If you see this page through the proxy, the stack is working.</p>
</body>
</html>
HTML
fi

# Launch the test site container
if [ ! "$(docker ps -q -f name=fake_website)" ]; then
  docker run -d --name fake_website \
    --network "$NETWORK_NAME" \
    -p 8081:80 \
    -v "$(pwd)/test_site:/usr/share/nginx/html:ro" \
    nginx:alpine
else
  echo "fake_website container already running"
fi

echo "Test site available at http://localhost:8081"
echo "Proxy via AI Scraping Defense at http://localhost:8080"
