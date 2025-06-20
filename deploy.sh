#!/bin/bash

# This script automates the deployment of the AI Scraping Defense system to a Kubernetes cluster.
# It ensures that resources are created in the correct order to prevent dependency issues.

# Exit immediately if a command exits with a non-zero status.
set -e

echo "🚀 Starting deployment to Kubernetes..."

# Step 1: Apply the Namespace
# The namespace must be created first, as all other resources will be placed within it.
echo "1. Applying namespace..."
kubectl apply -f kubernetes/namespace.yaml

# Step 2: Apply Configurations and Secrets
# These resources contain configuration data and secrets that other services depend on.
# They should be created before the applications that consume them.
echo "2. Applying ConfigMaps and Secrets..."
kubectl apply -f kubernetes/configmap.yaml
kubectl apply -f kubernetes/secrets.yaml
kubectl apply -f kubernetes/postgres-init-script-cm.yaml

# Step 3: Apply Persistent Volume Claims (PVCs)
# PVCs request storage from the cluster. Stateful applications will claim these volumes.
echo "3. Applying PersistentVolumeClaims..."
kubectl apply -f kubernetes/archives-pvc.yaml
kubectl apply -f kubernetes/corpus-pvc.yaml
kubectl apply -f kubernetes/models-pvc.yaml

# Step 4: Apply Stateful Backing Services (Databases, etc.)
# These are the core stateful applications like Postgres and Redis.
echo "4. Applying stateful services..."
kubectl apply -f kubernetes/postgres-statefulset.yaml
kubectl apply -f kubernetes/redis-statefulset.yaml

# Step 5: Apply Application Deployments
# These are the stateless application services that make up the system.
echo "5. Applying application deployments..."
kubectl apply -f kubernetes/admin-ui-deployment.yaml
kubectl apply -f kubernetes/ai-service-deployment.yaml
kubectl apply -f kubernetes/archive-rotator-deployment.yaml
kubectl apply -f kubernetes/escalation-engine-deployment.yaml
kubectl apply -f kubernetes/nginx-deployment.yaml
kubectl apply -f kubernetes/tarpit-api-deployment.yaml

# Step 6: Apply Jobs and CronJobs
# These are batch jobs or scheduled tasks.
echo "6. Applying jobs and cronjobs..."
kubectl apply -f kubernetes/corpus-updater-cronjob.yaml
kubectl apply -f kubernetes/markov-model-trainer.yaml
kubectl apply -f kubernetes/robots-fetcher-cronjob.yaml

echo "✅ Deployment complete. All resources have been applied to the 'ai-defense' namespace."

