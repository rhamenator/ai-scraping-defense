#!/bin/bash
#
# Deploys the entire AI Scraping Defense stack to the configured Kubernetes cluster.
#
# This script applies the manifests in a logical order to ensure dependencies
# like namespaces and secrets are created before the applications that use them.
#

# Use -e to exit immediately if a command fails
set -e

# Define the namespace for easy reference
NAMESPACE="ai-defense"
K8S_DIR="$(dirname "$0")/kubernetes"

echo "--- Starting Kubernetes Deployment for AI Scraping Defense ---"
echo "Target Namespace: $NAMESPACE"
echo "Manifests Directory: $K8S_DIR"
echo ""

# Step 1: Apply the Namespace first
echo "Step 1: Applying Namespace..."
kubectl apply -f "$K8S_DIR/namespace.yaml"
echo "Namespace applied."
echo ""

# Step 2: Apply all configurations and secrets.
# It's crucial these exist before pods that need them are created.
echo "Step 2: Applying ConfigMaps and Secrets..."
echo "Applying generic app configuration..."
kubectl apply -f "$K8S_DIR/configmap.yaml"
echo "Applying PostgreSQL init script..."
kubectl apply -f "$K8S_DIR/postgres-init-script-cm.yaml"
echo "Applying all generated secrets..."
# This assumes you have already run generate_secrets.sh to create this file.
if [ -f "$K8S_DIR/secrets.yaml" ]; then
    kubectl apply -f "$K8S_DIR/secrets.yaml"
else
    echo "ERROR: kubernetes/secrets.yaml not found. Please run generate_secrets.sh first."
    exit 1
fi
echo "Configurations and Secrets applied."
echo ""

# Step 3: Apply Persistent Volume Claims for storage.
echo "Step 3: Applying Persistent Volume Claims (PVCs)..."
kubectl apply -f "$K8S_DIR/archives-pvc.yaml"
kubectl apply -f "$K8S_DIR/corpus-pvc.yaml"
kubectl apply -f "$K8S_DIR/models-pvc.yaml"
echo "PVCs applied."
echo ""

# Step 4: Apply the stateful services (Database and Cache).
# These should be up and running before the main application pods start.
echo "Step 4: Applying Stateful Services (PostgreSQL, Redis)..."
kubectl apply -f "$K8S_DIR/postgres-statefulset.yaml"
kubectl apply -f "$K8S_DIR/redis-statefulset.yaml"
echo "Stateful services applied."
echo ""

# Step 5: Apply the main application deployments.
echo "Step 5: Applying Application Deployments..."
kubectl apply -f "$K8S_DIR/admin-ui-deployment.yaml"
kubectl apply -f "$K8S_DIR/ai-service-deployment.yaml"
kubectl apply -f "$K8S_DIR/escalation-engine-deployment.yaml"
kubectl apply -f "$K8S_DIR/tarpit-api-deployment.yaml"
kubectl apply -f "$K8S_DIR/archive-rotator-deployment.yaml"
echo "Application Deployments applied."
echo ""

# Step 6: Apply the CronJobs for scheduled tasks.
echo "Step 6: Applying CronJobs..."
kubectl apply -f "$K8S_DIR/corpus-updater-cronjob.yaml"
kubectl apply -f "$K8S_DIR/markov-model-trainer.yaml"
kubectl apply -f "$K8S_DIR/robots-fetcher-cronjob.yaml"
echo "CronJobs applied."
echo ""

# Step 7: Apply the Nginx ingress proxy.
# This is applied last as it depends on all the backend services being defined.
echo "Step 7: Applying Nginx Ingress Proxy..."
kubectl apply -f "$K8S_DIR/nginx-deployment.yaml"
echo "Nginx Ingress Proxy applied."
echo ""

echo "--- Deployment Complete ---"
echo "To monitor the status of your pods, run:"
echo "kubectl get pods -n $NAMESPACE -w"

