param(
    [string]$ProjectId = $env:GOOGLE_PROJECT_ID,
    [string]$ClusterName = $env:CLUSTER_NAME,
    [string]$Zone = $env:GKE_ZONE,
    [string]$ImageTag = 'latest'
)

if (-not $ProjectId) { $ProjectId = Read-Host 'GCP Project ID' }
if (-not $ClusterName) { $ClusterName = 'ai-defense-cluster' }
if (-not $Zone) { $Zone = 'us-central1-a' }

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
 gcloud container clusters get-credentials $ClusterName --zone $Zone

# Update image references in manifests
Get-ChildItem -Path kubernetes -Filter '*.yaml' -Recurse | ForEach-Object {
    (Get-Content $_.FullName) -replace 'your-registry/ai-scraping-defense:latest', $Image | Set-Content $_.FullName
}

# Generate secrets if needed
if (-not (Test-Path 'kubernetes/secrets.yaml')) {
    Write-Host 'Generating secrets file'
    ./scripts/windows/Generate-Secrets.ps1
}

# Deploy manifests
./deploy.ps1

Write-Host 'Deployment complete. View pods with: kubectl get pods -n ai-defense'
