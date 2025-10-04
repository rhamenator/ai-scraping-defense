#!/usr/bin/env bash
# Deploy the AI Scraping Defense stack to Google Kubernetes Engine
set -euo pipefail

# OS guard: Linux only
if [ "$(uname -s)" != "Linux" ]; then
  echo "Unsupported OS: $(uname -s). This entrypoint supports Linux only." >&2
  echo "Use scripts/macos/*.zsh on macOS or scripts/windows/*.ps1 on Windows." >&2
  exit 1
fi

PROJECT_ID="${PROJECT_ID:-${GOOGLE_PROJECT_ID:-your-gcp-project}}"
CLUSTER_NAME="${CLUSTER_NAME:-ai-defense-cluster}"
GKE_ZONE="${GKE_ZONE:-us-central1-a}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
IMAGE="gcr.io/$PROJECT_ID/ai-scraping-defense:$IMAGE_TAG"

# Ensure commands run from repository root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"
# Build and push the Docker image
echo "Building Docker image $IMAGE"
gcloud auth configure-docker --quiet

docker build -t "$IMAGE" .
docker push "$IMAGE"

# Create the cluster if it does not exist
if ! gcloud container clusters describe "$CLUSTER_NAME" --zone "$GKE_ZONE" >/dev/null 2>&1; then
  echo "Creating GKE cluster $CLUSTER_NAME"
  gcloud container clusters create "$CLUSTER_NAME" \
    --zone "$GKE_ZONE" --num-nodes 3
fi

# Configure kubectl
 gcloud container clusters get-credentials "$CLUSTER_NAME" --zone "$GKE_ZONE"

# Update image references in manifests
find kubernetes -name '*.yaml' -print0 | xargs -0 sed -i "s|your-registry/ai-scraping-defense:latest|$IMAGE|g"

# Generate secrets if missing
if [ ! -f kubernetes/secrets.yaml ]; then
  echo "Generating secrets file"
  bash "$SCRIPT_DIR/generate_secrets.sh"
fi

# Deploy the manifests
bash "$SCRIPT_DIR/deploy.sh"

echo "Deployment complete. View pods with: kubectl get pods -n ai-defense"
