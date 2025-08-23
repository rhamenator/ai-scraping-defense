# Cloud Provider Deployment (GKE Example)

This guide explains how to deploy the AI Scraping Defense stack to **Google Kubernetes Engine (GKE)**. The process is similar for other managed Kubernetes services such as Amazon EKS or Azure AKS.

## Prerequisites

- A Google Cloud project with billing enabled.
- The [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) with `gcloud` and `kubectl` available in your path.
- Docker configured to push images to Google Container Registry (GCR).
- A copy of this repository cloned locally.

## Manual Deployment Steps

1. **Build and Push the Docker Image**

   ```bash
   export PROJECT_ID="your-gcp-project"
   export IMAGE="gcr.io/$PROJECT_ID/ai-scraping-defense:latest"

   # Authenticate with Google Cloud and build the image
   gcloud auth configure-docker
   docker build -t "$IMAGE" .
   docker push "$IMAGE"
   ```

2. **Create or Reuse a GKE Cluster**

   ```bash
   export CLUSTER_NAME="ai-defense-cluster"
   export GKE_ZONE="us-central1-a"

   gcloud container clusters create "$CLUSTER_NAME" \
       --zone "$GKE_ZONE" --num-nodes 3
   gcloud container clusters get-credentials "$CLUSTER_NAME" --zone "$GKE_ZONE"
   ```

3. **Generate Kubernetes Secrets**

   Run the provided script to create `kubernetes/secrets.yaml`:

   ```bash
   ./scripts/linux/generate_secrets.sh
   ```

   Replace the placeholder API keys in `kubernetes/secrets.yaml` with your actual base64‑encoded credentials before applying.

4. **Update Image References**

   Search the manifests under `kubernetes/` for the `image:` field and replace the default placeholder with your `$IMAGE` path.

5. **Deploy the Manifests**

   Apply the Kubernetes resources using the helper script:

   ```bash
   ./deploy.sh
   ```

6. **Verify the Deployment**

   ```bash
   kubectl get pods -n ai-defense
   kubectl get svc -n ai-defense
   ```

   Once the pods are running, access the service using the external IP of the `nginx-proxy` service.

## Automated Deployment

For convenience, scripts are provided to automate these steps:

- `gke_deploy.sh` &ndash; Bash script for Linux/macOS
- `gke_deploy.ps1` &ndash; PowerShell script for Windows

The scripts build and push the image, create the cluster if it does not already exist, and then invoke `deploy.sh` / `deploy.ps1` to apply the manifests.

```bash
./gke_deploy.sh
```

```powershell
./gke_deploy.ps1
```

Customize environment variables such as `PROJECT_ID`, `CLUSTER_NAME`, and `GKE_ZONE` before running the scripts to suit your Google Cloud environment.
