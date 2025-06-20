<#
.SYNOPSIS
    Automates the deployment of the AI Scraping Defense system to a Kubernetes cluster.
.DESCRIPTION
    This PowerShell script ensures that all Kubernetes resources are created in the
    correct order to prevent dependency issues. It is designed to be run from a
    Windows environment where kubectl is installed and configured.
.NOTES
    Author: Your Name
    Date: 2025-06-19
#>

# Stop the script immediately if any command fails.
$ErrorActionPreference = "Stop"

try {
    Write-Host "🚀 Starting deployment to Kubernetes..." -ForegroundColor Green

    # Step 1: Apply the Namespace
    # The namespace must be created first, as all other resources will be placed within it.
    Write-Host "1. Applying namespace..." -ForegroundColor Cyan
    kubectl apply -f kubernetes\namespace.yaml

    # Step 2: Apply Configurations and Secrets
    # These resources contain configuration data and secrets that other services depend on.
    Write-Host "2. Applying ConfigMaps and Secrets..." -ForegroundColor Cyan
    kubectl apply -f kubernetes\configmap.yaml
    kubectl apply -f kubernetes\secrets.yaml
    kubectl apply -f kubernetes\postgres-init-script-cm.yaml

    # Step 3: Apply Persistent Volume Claims (PVCs)
    # PVCs request storage from the cluster. Stateful applications will claim these volumes.
    Write-Host "3. Applying PersistentVolumeClaims..." -ForegroundColor Cyan
    kubectl apply -f kubernetes\archives-pvc.yaml
    kubectl apply -f kubernetes\corpus-pvc.yaml
    kubectl apply -f kubernetes\models-pvc.yaml

    # Step 4: Apply Stateful Backing Services (Databases, etc.)
    # These are the core stateful applications like Postgres and Redis.
    Write-Host "4. Applying stateful services..." -ForegroundColor Cyan
    kubectl apply -f kubernetes\postgres-statefulset.yaml
    kubectl apply -f kubernetes\redis-statefulset.yaml

    # Step 5: Apply Application Deployments
    # These are the stateless application services that make up the system.
    Write-Host "5. Applying application deployments..." -ForegroundColor Cyan
    kubectl apply -f kubernetes\admin-ui-deployment.yaml
    kubectl apply -f kubernetes\ai-service-deployment.yaml
    kubectl apply -f kubernetes\archive-rotator-deployment.yaml
    kubectl apply -f kubernetes\escalation-engine-deployment.yaml
    kubectl apply -f kubernetes\nginx-deployment.yaml
    kubectl apply -f kubernetes\tarpit-api-deployment.yaml

    # Step 6: Apply Jobs and CronJobs
    # These are batch jobs or scheduled tasks.
    Write-Host "6. Applying jobs and cronjobs..." -ForegroundColor Cyan
    kubectl apply -f kubernetes\corpus-updater-cronjob.yaml
    kubectl apply -f kubernetes\markov-model-trainer.yaml
    kubectl apply -f kubernetes\robots-fetcher-cronjob.yaml

    Write-Host "✅ Deployment complete. All resources have been applied to the 'ai-defense' namespace." -ForegroundColor Green
}
catch {
    Write-Host "❌ Deployment failed." -ForegroundColor Red
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    # Exit with a non-zero status code to indicate failure
    exit 1
}

