#!/usr/bin/env bash
set -euo pipefail

echo "Creating necessary local directories for AI Scraping Defense Stack..."

mkdir -p config
mkdir -p data
mkdir -p db
mkdir -p logs
mkdir -p logs/nginx
mkdir -p models
mkdir -p archives
mkdir -p secrets
mkdir -p nginx/errors
# TLS certificate directory matching TLS_CERT_PATH and TLS_KEY_PATH in .env
mkdir -p nginx/certs
# The kubernetes directory should already exist if you cloned the repo.

if command -v openssl >/dev/null 2>&1; then
    if [[ ! -f nginx/certs/tls.key || ! -f nginx/certs/tls.crt ]]; then
        echo "Generating a self-signed TLS certificate for local HTTPS..."
        openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
            -keyout nginx/certs/tls.key \
            -out nginx/certs/tls.crt \
            -subj "/CN=localhost"
        chmod 600 nginx/certs/tls.key
    fi
else
    echo "OpenSSL not found; skipping TLS certificate generation."
fi

echo "Creating placeholder secret files in ./secrets/ (REMEMBER TO FILL THESE WITH ACTUAL VALUES):"
touch ./secrets/pg_password.txt
touch ./secrets/redis_password.txt # Optional, if you use Redis auth
touch ./secrets/smtp_password.txt
touch ./secrets/external_api_key.txt
touch ./secrets/ip_reputation_api_key.txt
touch ./secrets/community_blocklist_api_key.txt
# For Kubernetes, SYSTEM_SEED is directly in secrets.yaml data, not a file.
# For Docker Compose, you might set SYSTEM_SEED in .env or a secrets file if you adapt it.

echo "---------------------------------------------------------------------"
echo "IMPORTANT REMINDERS:"
echo "1. Place your actual 'robots.txt' into the './config/' directory."
echo "2. Place your 'init_markov.sql' (PostgreSQL schema) into the './db/' directory."
echo "3. Populate all files in './secrets/' with your actual secret values."
echo "4. For Kubernetes: Ensure you have created 'kubernetes/postgres-init-script-cm.yaml'."
echo "5. For Kubernetes: Ensure you have updated 'kubernetes/secrets.yaml' with your base64 encoded secrets (including SYSTEM_SEED)."
echo "6. Build your Docker images, push them to a registry, and update ALL 'image:' fields in your Kubernetes YAML files."
echo "---------------------------------------------------------------------"
echo "Directory structure setup complete."
