# Kubernetes Deployment Guide

This guide outlines the steps to deploy the AI Scraping Defense stack to a Kubernetes cluster.

## Prerequisites

- A running Kubernetes cluster.
- `kubectl` configured to communicate with your cluster.
- A container registry (e.g., Docker Hub, Google Container Registry, GitHub Container Registry) to store your built Docker image.

### Deploy with Helm

The repository now ships with a basic Helm chart located in the `helm/ai-scraping-defense` directory. Using Helm simplifies deployment and enables optional Horizontal Pod Autoscaler (HPA) resources.

```bash
helm install ai-defense ./helm/ai-scraping-defense \
  --set image.repository=your-registry/ai-scraping-defense \
  --set image.tag=latest
```

Customize the values in `values.yaml` or via `--set` flags to tune replica counts and autoscaling limits for large clusters.

## Deployment Steps

### 1. Build and Push the Docker Image

If you are using Docker Hub, you can log in with:

``` bash
docker login
```

The project uses a single `Dockerfile` in the root directory to build a base image for all Python services.

```bash  
# Replace 'your-registry/your-repo' with your actual container registry path  
export IMAGE_NAME="your-registry/your-repo/ai-scraping-defense:latest"
# Build the image  
docker build -t $IMAGE_NAME .
# Push the image to your registry  
docker push $IMAGE_NAME
```

This command builds the Docker image and tags it with the specified name. Ensure you have logged in to your container registry before pushing the image.

### **2. Update Deployment Manifests**

You must update all the Kubernetes Deployment and CronJob manifests in the kubernetes/ directory to use the image you just pushed.

Search for the image: key in all *.yaml files inside kubernetes/ and replace the placeholder value (e.g., your-registry/ai-scraping-defense:latest) with the $IMAGE_NAME you defined above.

### **Enable ModSecurity**

1. Download the OWASP CRS into the `waf/` directory so that `crs-setup.conf` and a `rules` folder are available.
2. Create the `waf-rules` ConfigMap:
   ```bash
   kubectl create configmap waf-rules --from-file=waf/ -n ai-defense
   ```
3. Apply the manifests which mount `/etc/nginx/modsecurity` in the Nginx deployment.

### **3. Generate and Apply Secrets**

The application's secrets (passwords, API keys) are managed via a single secrets.yaml file, which should **never** be committed to version control.

First, run the secret generation script:

- **On Linux/macOS:** bash ./generate_secrets.sh
- **On Windows:** .Generate-Secrets.ps1

This creates a `kubernetes/secrets.yaml` file with securely generated, base64-encoded values and prints the plaintext credentials to your console.

**IMPORTANT:** Before applying, open kubernetes/secrets.yaml and replace the placeholder API keys (e.g., YOUR_BASE64_ENCODED_OPENAI_API_KEY) with your actual, base64-encoded keys if you plan to use those services.

Now, apply the secrets manifest to your cluster:

``` bash or PowerShell
kubectl apply -f kubernetes/secrets.yaml
```

### **4. Deploy the Application**

The Kubernetes manifests are organized in the kubernetes/ directory. Each service, database, and configuration is defined in its own YAML file.
You can deploy the entire stack by applying all the manifest files in the kubernetes/ directory. It's best practice to apply them in a logical order.

This deployment can be accomplished by running:

```bash
sudo bash ./kubernetes/deploy.sh
```

```PowerShell
# This must be run in an administrator PowerShell terminal
.\kubernetes\deploy.ps1
```

or by running `kubectl apply -f` for each file individually. You can also use a tool like `kustomize` to manage the deployment if you prefer a more structured approach.

If you are manually applying `kubectl apply -f` to each file, it should be done in the correct order. Here’s a recommended sequence:

``` bash or PowerShell
# 1. Create the namespace
kubectl apply -f kubernetes/namespace.yaml

# 2. Create the ConfigMap and Persistent Volume Claims
kubectl apply -f kubernetes/configmap.yaml
kubectl apply -f kubernetes/archives-pvc.yaml
kubectl apply -f kubernetes/corpus-pvc.yaml
kubectl apply -f kubernetes/models-pvc.yaml

# 3. Deploy the stateful services (Database and Cache)
kubectl apply -f kubernetes/postgres-statefulset.yaml
kubectl apply -f kubernetes/redis-statefulset.yaml

# 4. Deploy the application microservices
kubectl apply -f kubernetes/admin-ui-deployment.yaml
kubectl apply -f kubernetes/ai-service-deployment.yaml
kubectl apply -f kubernetes/escalation-engine-deployment.yaml
kubectl apply -f kubernetes/tarpit-api-deployment.yaml
kubectl apply -f kubernetes/archive-rotator-deployment.yaml

# 5. Deploy the CronJobs
kubectl apply -f kubernetes/corpus-updater-cronjob.yaml
kubectl apply -f kubernetes/markov-model-trainer.yaml
kubectl apply -f kubernetes/robots-fetcher-cronjob.yaml

# 6. Deploy the Nginx ingress proxy
kubectl apply -f kubernetes/nginx-deployment.yaml
```

### 5. **Verify the Deployment**

Check the status of your pods to ensure everything is running correctly:

```bash or PowerShell
kubectl get pods -n ai-defense -w
```

Once all pods are in the Running state, you can find the external IP address of your Nginx service to access the application:

```bash or PowerShell
kubectl get svc -n ai-defense nginx-proxy  
```

### 6. **Access the Application**

Open your web browser and navigate to the external IP address of the Nginx service. You should see the admin UI of the AI Scraping Defense application. The instructions for accessing the application are in getting_started.md.
