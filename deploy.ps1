<#
.SYNOPSIS
    Deploys the entire AI Scraping Defense stack to the configured Kubernetes cluster.

.DESCRIPTION
    This script applies the manifests in a logical order to ensure dependencies
    like namespaces and secrets are created before the applications that use them.
#>

# --- Script Configuration ---
$ErrorActionPreference = "Stop"
$Namespace = "ai-defense"
$K8sDir = Join-Path $PSScriptRoot "kubernetes"

Write-Host "--- Starting Kubernetes Deployment for AI Scraping Defense ---" -ForegroundColor Yellow
Write-Host "Target Namespace: $Namespace"
Write-Host "Manifests Directory: $K8sDir"
Write-Host ""

# --- Deployment Steps ---

# Step 1: Apply the Namespace first
Write-Host "Step 1: Applying Namespace..." -ForegroundColor Cyan
kubectl apply -f (Join-Path $K8sDir "namespace.yaml")
Write-Host "Namespace applied."
Write-Host ""

# Step 2: Apply all configurations, secrets, and RBAC.
Write-Host "Step 2: Applying ConfigMaps, Secrets, and RBAC..." -ForegroundColor Cyan
Write-Host "Applying generic app configuration..."
kubectl apply -f (Join-Path $K8sDir "configmap.yaml")
Write-Host "Applying PostgreSQL init script..."
kubectl apply -f (Join-Path $K8sDir "postgres-init-script-cm.yaml")
Write-Host "Applying all generated secrets..."
# This assumes you have already run Generate-Secrets.ps1 to create this file.
$secretsFile = Join-Path $K8sDir "secrets.yaml"
if (Test-Path $secretsFile) {
    kubectl apply -f $secretsFile
}
else {
    Write-Error "ERROR: kubernetes\secrets.yaml not found. Please run Generate-Secrets.ps1 first."
    exit 1
}
Write-Host "Applying robots fetcher RBAC..."
kubectl apply -f (Join-Path $K8sDir "robots-fetcher-rbac.yaml")
Write-Host "Configurations and Secrets applied."
Write-Host ""

# Step 3: Apply Persistent Volume Claims for storage.
Write-Host "Step 3: Applying Persistent Volume Claims (PVCs)..." -ForegroundColor Cyan
kubectl apply -f (Join-Path $K8sDir "archives-pvc.yaml")
kubectl apply -f (Join-Path $K8sDir "corpus-pvc.yaml")
kubectl apply -f (Join-Path $K8sDir "models-pvc.yaml")
Write-Host "PVCs applied."
Write-Host ""

# Step 4: Apply the stateful services (Database and Cache).
Write-Host "Step 4: Applying Stateful Services (PostgreSQL, Redis)..." -ForegroundColor Cyan
kubectl apply -f (Join-Path $K8sDir "postgres-statefulset.yaml")
kubectl apply -f (Join-Path $K8sDir "redis-statefulset.yaml")
Write-Host "Stateful services applied."
Write-Host ""

# Step 5: Apply the main application deployments.
Write-Host "Step 5: Applying Application Deployments..." -ForegroundColor Cyan
kubectl apply -f (Join-Path $K8sDir "admin-ui-deployment.yaml")
kubectl apply -f (Join-Path $K8sDir "ai-service-deployment.yaml")
kubectl apply -f (Join-Path $K8sDir "escalation-engine-deployment.yaml")
kubectl apply -f (Join-Path $K8sDir "tarpit-api-deployment.yaml")
kubectl apply -f (Join-Path $K8sDir "archive-rotator-deployment.yaml")
Write-Host "Application Deployments applied."
Write-Host ""

# Step 6: Apply the CronJobs for scheduled tasks.
Write-Host "Step 6: Applying CronJobs..." -ForegroundColor Cyan
kubectl apply -f (Join-Path $K8sDir "corpus-updater-cronjob.yaml")
kubectl apply -f (Join-Path $K8sDir "markov-model-trainer.yaml")
kubectl apply -f (Join-Path $K8sDir "robots-fetcher-cronjob.yaml")
Write-Host "CronJobs applied."
Write-Host ""

# Step 7: Apply the Nginx ingress proxy.
Write-Host "Step 7: Applying Nginx Ingress Proxy..." -ForegroundColor Cyan
kubectl apply -f (Join-Path $K8sDir "nginx-deployment.yaml")
Write-Host "Nginx Ingress Proxy applied."
Write-Host ""

Write-Host "--- Deployment Complete ---" -ForegroundColor Green
Write-Host "To monitor the status of your pods, run:"
Write-Host "kubectl get pods -n $Namespace -w"
