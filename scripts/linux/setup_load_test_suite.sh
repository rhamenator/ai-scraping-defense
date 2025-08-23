#!/bin/bash
# =============================================================================
#  setup_load_test_suite.sh - install basic load testing tools
#
#  This helper installs a few common utilities for stress testing the
#  AI Scraping Defense stack. Use only against infrastructure you own
#  or are authorized to test.
# =============================================================================
set -e

echo "=== Installing load testing tools ==="

# Determine package manager
if command -v apt-get >/dev/null; then
    PKG_MANAGER="apt-get"
elif command -v yum >/dev/null; then
    PKG_MANAGER="yum"
else
    echo "Unsupported package manager. Install wrk, siege, and apache2-utils manually."
    exit 1
fi

sudo $PKG_MANAGER update -y
sudo $PKG_MANAGER install -y wrk siege apache2-utils

# Install k6 if missing
if ! command -v k6 >/dev/null; then
    echo "Installing k6..."
    if [ "$PKG_MANAGER" = "apt-get" ]; then
        sudo apt-get install -y gnupg2 curl
        curl -fsSL https://dl.k6.io/key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/k6-archive-keyring.gpg
        echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
        sudo apt-get update
        sudo apt-get install -y k6
    else
        sudo yum install -y k6
    fi
fi

# Install Locust via pip
if ! command -v locust >/dev/null; then
    pip install --user locust
fi

cat <<'MSG'

Load testing tools installed.
Example commands:
  wrk -t4 -c100 -d30s http://localhost:8080
  siege -c50 -t1m http://localhost:8080
  ab -n 1000 -c100 http://localhost:8080/
  k6 run examples/script.js
  locust -f examples/locustfile.py

Ensure you have permission before running tests.
MSG
