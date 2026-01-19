# Optional env overrides:
# - KUBE_CONTEXT: kubectl context to use instead of gcloud credentials
# - KUBE_NAMESPACE: namespace to deploy into (default: ai-defense)
param(
    [string]$ProjectId = $env:GOOGLE_PROJECT_ID,
    [string]$ClusterName = $env:CLUSTER_NAME,
    [string]$Zone = $env:GKE_ZONE,
    [string]$ImageTag = 'latest',
    [string]$KubeContext = $env:KUBE_CONTEXT,
    [string]$KubeNamespace = $env:KUBE_NAMESPACE
)

if (-not $ProjectId) { $ProjectId = Read-Host 'GCP Project ID' }
if (-not $ClusterName) { $ClusterName = 'ai-defense-cluster' }
if (-not $Zone) { $Zone = 'us-central1-a' }
if (-not $KubeNamespace) { $KubeNamespace = 'ai-defense' }

$Image = "gcr.io/$ProjectId/ai-scraping-defense:$ImageTag"

Write-Host "Building Docker image $Image"
& gcloud auth configure-docker --quiet

docker build -t $Image .
docker push $Image

# Create cluster if it does not exist
& gcloud container clusters describe $ClusterName --zone $Zone 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating GKE cluster $ClusterName"
    gcloud container clusters create $ClusterName --zone $Zone --num-nodes 3
}

# Configure kubectl
if ($KubeContext) {
    Write-Host "Using KUBE_CONTEXT=$KubeContext for kubectl context override."
    kubectl config use-context $KubeContext
} else {
    gcloud container clusters get-credentials $ClusterName --zone $Zone
}

# Update image references in manifests
Get-ChildItem -Path kubernetes -Filter '*.yaml' -Recurse | ForEach-Object {
    (Get-Content $_.FullName) -replace 'your-registry/ai-scraping-defense:latest', $Image | Set-Content $_.FullName
}
if ($KubeNamespace -ne 'ai-defense') {
    Write-Host "Updating namespace references to $KubeNamespace"
    Get-ChildItem -Path kubernetes -Filter '*.yaml' -Recurse | ForEach-Object {
        (Get-Content $_.FullName) -replace 'namespace: ai-defense', \"namespace: $KubeNamespace\" | Set-Content $_.FullName
    }
}

# Generate secrets if needed
if (-not (Test-Path 'kubernetes/secrets.yaml')) {
    Write-Host 'Generating secrets file'
    ./scripts/windows/Generate-Secrets.ps1
}

# Deploy manifests
$env:KUBE_NAMESPACE = $KubeNamespace
./deploy.ps1

Write-Host \"Deployment complete. View pods with: kubectl get pods -n $KubeNamespace\"
