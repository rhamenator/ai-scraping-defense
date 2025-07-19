#!/bin/bash
# Quick deployment for Kubernetes
set -e

echo "=== AI Scraping Defense: Quick Deploy ==="

# Ensure .env exists for docker build context or other scripts
if [ ! -f .env ]; then
  cp sample.env .env
  echo "Created .env from sample.env"
fi

# Generate Kubernetes secrets
bash ./generate_secrets.sh

# Deploy to Kubernetes
bash ./deploy.sh

echo "Deployment complete. Monitor pods with: kubectl get pods -n ai-defense"
