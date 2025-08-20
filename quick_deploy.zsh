#!/bin/zsh
# Quick deployment for Kubernetes
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== AI Scraping Defense: Quick Deploy ==="

# Ensure .env exists for docker build context or other scripts
if [ ! -f .env ]; then
  cp sample.env .env
  echo "Created .env from sample.env"
fi

# Deploy to Kubernetes
bash ./deploy.sh

echo "Deployment complete. Monitor pods with: kubectl get pods -n ai-defense"
