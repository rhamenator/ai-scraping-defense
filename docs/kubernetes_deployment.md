# Kubernetes Deployment Guide

This guide provides instructions for deploying the AI Scraping Defense Stack on a Kubernetes cluster using the provided manifest files located in the `/kubernetes` directory. This guide assumes you are using version 0.0.4 or later of the stack.

## 0. Before You Begin: Clone the Repository

If you haven't already, clone the project repository to your local machine:

```bash
git clone [https://github.com/rhamenator/ai-scraping-defense.git](https://github.com/rhamenator/ai-scraping-defense.git) # Or your fork
cd ai-scraping-defense
```

Ensure your `Dockerfile.txt` is renamed to `Dockerfile` in the project root.

## 1. Prerequisites

* **Kubernetes Cluster:** Access to a functioning Kubernetes cluster (e.g., Minikube, Kind, k3s, Docker Desktop Kubernetes, or a managed cloud provider cluster like GKE, EKS, AKS). Version 1.21+ recommended.
* **`kubectl`:** The Kubernetes command-line tool, configured to interact with your cluster. ([Install kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl/))
* **Persistent Storage:** Your cluster must have a default StorageClass configured, or you need to define one and update the `PersistentVolumeClaim` definitions if needed. Persistent storage is required for PostgreSQL, Redis, model storage, honeypot archives, and the dynamic corpus.
* **Docker Image Registry:** You need a container image registry (like Docker Hub, Google Artifact Registry, Amazon ECR, GitHub Container Registry, Harbor, etc.) accessible by your Kubernetes cluster.
* **Base64 utility:** For encoding secret values (usually available by default on Linux/macOS).
* **Text Editor:** For modifying configuration files.

## 2. Overview of Kubernetes Manifests

The `/kubernetes` directory contains YAML manifests for deploying each component within the `ai-defense` namespace. Key resources include:

* **Namespace:** All resources are deployed into the `ai-defense` namespace.
* **`kubernetes/configmap.yaml`:** Defines non-sensitive configuration. `SYSTEM_SEED` is now managed via a Secret.
* **`kubernetes/secrets.yaml`:** Defines structures for sensitive data (API keys, passwords, `SYSTEM_SEED`). **You MUST populate this with your actual secrets.**
* **`kubernetes/postgres-init-script-cm.yaml` (New):** A ConfigMap you will create to hold the `init_markov.sql` script for automatic PostgreSQL schema initialization.
* **PersistentVolumeClaims (PVCs):**
  * `kubernetes/archives-pvc.yaml` (defines `archives-pvc`)
  * `kubernetes/corpus-pvc.yaml` (defines `corpus-data-pvc`)
  * `kubernetes/models-pvc.yaml` (defines `models-pvc`)
  * The PVCs for PostgreSQL (`postgres-persistent-storage`) and Redis (`redis-data`) are defined within their respective StatefulSet YAML files.
* **StatefulSets:**
  * `kubernetes/redis-statefulset.yaml`
  * `kubernetes/postgres-statefulset.yaml` (now includes automated schema initialization using `postgres-init-script-cm.yaml`)
* **Deployments:** For all stateless services (`nginx`, `tarpit-api`, `escalation-engine`, `ai-service`, `admin-ui`, `archive-rotator`).
* **CronJobs:**
  * `kubernetes/corpus-updater-cronjob.yaml` (for dynamic Wikipedia corpus)
  * `kubernetes/robots-fetcher-cronjob.yaml` (for dynamic `robots.txt`)
  * `kubernetes/markov-model-trainer.yaml` (for training PostgreSQL Markov model from the corpus)
* **Services:** For exposing applications within the cluster or externally (Nginx).
* **RBAC:** `kubernetes/robots-fetcher-cronjob.yaml` includes necessary ServiceAccount, Role, and RoleBinding.

## 3. Configuration Steps

1. **Build and Push Docker Images:**
    * The stack uses two primary custom Docker images:
        * One for all Python services (placeholder: `your-registry/ai-defense-python-base:latest`).
        * One for Nginx (placeholder: `your-registry/ai-defense-nginx:latest`).
    * Build your images using the provided `Dockerfile` from the project root.

        ```bash
        # Example for Python base image (replace with your actual registry and desired tag)
        docker build -t your-registry/your-username/ai-defense-python-base:v0.0.4 .
        docker push your-registry/your-username/ai-defense-python-base:v0.0.4

        # Example for Nginx image (if you have a separate Dockerfile.nginx or build stage)
        # For simplicity, the main Dockerfile can be structured to produce both, or you can have two.
        # If using the same Dockerfile and just changing the CMD/ENTRYPOINT for Nginx service,
        # you might use the same Python base image and override command in nginx-deployment.yaml,
        # or build a dedicated Nginx image.
        # Assuming a dedicated Nginx image:
        # docker build -f Dockerfile.nginx -t your-registry/your-username/ai-defense-nginx:v0.0.4 .
        # docker push your-registry/your-username/ai-defense-nginx:v0.0.4
        ```

    * **Update Kubernetes Manifests with Your Image URIs:**
        Go through all `*-deployment.yaml` and `*-cronjob.yaml` files in the `kubernetes/` directory. In each file, find the `spec.template.spec.containers[0].image` (or similar path for CronJobs) field. Replace the placeholder image URIs:
        * `your-registry/ai-defense-python-base:latest` with your actual Python base image URI (e.g., `docker.io/yourusername/ai-defense-python-base:v0.0.4`).
        * `your-registry/ai-defense-nginx:latest` with your actual Nginx image URI.
        * **It is highly recommended to use specific version tags (like `v0.0.4`) instead of `latest` for production and reproducible deployments.**

2. **Prepare Secrets (`kubernetes/secrets.yaml`):**
    * Open `kubernetes/secrets.yaml`.
    * **`SYSTEM_SEED` (in `system-seed-secret`):** This is critical. Generate a strong, unique random string, base64 encode it, and replace the placeholder value.

        ```bash
        echo -n 'YOUR_VERY_SECURE_AND_RANDOM_SYSTEM_SEED_STRING' | base64
        ```

    * **Other Secrets:** Similarly, for `smtp-credentials`, `external-api-credentials`, `ip-reputation-credentials`, `community-blocklist-credentials`, `postgres-credentials`, and `redis-credentials`, replace the placeholder `data` values with your actual base64-encoded secrets.

3. **Review ConfigMap (`kubernetes/configmap.yaml`):**
    * Open `kubernetes/configmap.yaml`.
    * **`REAL_BACKEND_HOST`**: Ensure this points to the correct internal Kubernetes service name and port of your actual web application that Nginx should proxy legitimate traffic to (e.g., `http://my-app-service.ai-defense.svc.cluster.local:8080`).
    * Review other settings (Tarpit, Redis, PostgreSQL, Alerting, External APIs, etc.) and adjust if necessary. `SYSTEM_SEED` is no longer in this file.

4. **Create PostgreSQL Init Script ConfigMap (`kubernetes/postgres-init-script-cm.yaml`):**
    * Create a new file named `kubernetes/postgres-init-script-cm.yaml`.
    * Paste the ConfigMap definition (containing your `db/init_markov.sql` content) into this file, as provided in the previous instructions. This script will be used to automatically initialize the PostgreSQL schema.

5. **PersistentVolumeClaims (PVCs):**
    * Review the storage requests in:
        * `kubernetes/archives-pvc.yaml` (`archives-pvc`)
        * `kubernetes/corpus-pvc.yaml` (`corpus-data-pvc`)
        * `kubernetes/models-pvc.yaml` (`models-pvc`)
        * The `volumeClaimTemplates` sections within `kubernetes/postgres-statefulset.yaml` (for `postgres-persistent-storage`) and `kubernetes/redis-statefulset.yaml` (for `redis-data`).
    * Adjust `spec.resources.requests.storage` if needed. If your cluster doesn't use a default StorageClass, you might need to specify a `storageClassName` in the PVC specs.

## 4. Deployment Steps

Ensure `kubectl` is configured for your target Kubernetes cluster.

1. **Create Namespace:**

    ```bash
    kubectl create namespace ai-defense
    ```

2. **Apply ConfigMaps:**

    ```bash
    kubectl apply -f kubernetes/configmap.yaml -n ai-defense
    kubectl apply -f kubernetes/postgres-init-script-cm.yaml -n ai-defense
    ```

3. **Apply Secrets:**

    ```bash
    kubectl apply -f kubernetes/secrets.yaml -n ai-defense
    ```

4. **Apply PersistentVolumeClaims (standalone ones):**

    ```bash
    kubectl apply -f kubernetes/archives-pvc.yaml -n ai-defense
    kubectl apply -f kubernetes/corpus-pvc.yaml -n ai-defense
    kubectl apply -f kubernetes/models-pvc.yaml -n ai-defense
    ```

    *(PVCs for PostgreSQL and Redis are created automatically by their StatefulSets).*

5. **Apply StatefulSets (Redis & PostgreSQL):**

    ```bash
    kubectl apply -f kubernetes/redis-statefulset.yaml -n ai-defense
    kubectl apply -f kubernetes/postgres-statefulset.yaml -n ai-defense
    ```

    Monitor their creation and wait for them to become ready:

    ```bash
    kubectl get pods -n ai-defense -l app=redis -w
    kubectl get pods -n ai-defense -l app=postgres-markov -w
    ```

    PostgreSQL will run the `init_markov.sql` script automatically on its first startup if the persistent volume is empty.

6. **Apply Deployments:**
    *(Ensure you have updated the `image:` fields in these files first!)*

    ```bash
    kubectl apply -f kubernetes/ai-service-deployment.yaml -n ai-defense
    kubectl apply -f kubernetes/escalation-engine-deployment.yaml -n ai-defense
    kubectl apply -f kubernetes/tarpit-api-deployment.yaml -n ai-defense
    kubectl apply -f kubernetes/admin-ui-deployment.yaml -n ai-defense
    kubectl apply -f kubernetes/archive-rotator-deployment.yaml -n ai-defense
    kubectl apply -f kubernetes/nginx-deployment.yaml -n ai-defense
    ```

7. **Apply CronJobs:**
    *(Ensure you have updated the `image:` fields in these files first!)*

    ```bash
    kubectl apply -f kubernetes/robots-fetcher-cronjob.yaml -n ai-defense
    kubectl apply -f kubernetes/corpus-updater-cronjob.yaml -n ai-defense
    kubectl apply -f kubernetes/markov-model-trainer.yaml -n ai-defense
    ```

8. **Verify Pods, Services, and CronJobs:**

    ```bash
    kubectl get pods -n ai-defense
    kubectl get services -n ai-defense
    kubectl get cronjobs -n ai-defense
    ```

    Ensure all pods transition to the `Running` state. Check logs for any startup errors: `kubectl logs <pod-name> -n ai-defense -c <container-name-if-multiple>`.

## 5. Accessing Services

* **Nginx (Main Entry Point):** If the `nginx` service in `kubernetes/nginx-deployment.yaml` is of type `LoadBalancer`, your cloud provider will provision an external IP. Find it with:

    ```bash
    kubectl get svc nginx -n ai-defense
    ```

    If it's `NodePort`, access via `<NodeIP>:<NodePort>`. For production environments, using an **Ingress** controller is highly recommended for managing external access, TLS termination, and host-based routing.
* **Admin UI:** Typically accessed via Nginx (e.g., `http://<nginx-external-ip>/admin/`).
* Other services are usually type `ClusterIP` and are accessed internally within the Kubernetes cluster using their service names (e.g., `http://tarpit-api.ai-defense.svc.cluster.local:8001`).

## 6. Testing & Verification

* Follow similar testing steps as outlined in the Docker Compose `docs/getting_started.md`, but use the Kubernetes Nginx external IP/hostname.
* Check CronJob execution:

    ```bash
    kubectl get jobs -n ai-defense # Lists jobs created by CronJobs
    kubectl logs job/<job-name> -n ai-defense # View logs for a specific job
    ```

* Inspect ConfigMaps updated by CronJobs (e.g., `kubectl get configmap live-robots-txt-config -n ai-defense -o yaml`).
* Verify data in PVCs if necessary (e.g., by exec-ing into a pod that mounts them and listing directory contents).

## 7. Production Considerations

* **Ingress Controller:** Essential for robust external access management.
* **Resource Requests/Limits:** Fine-tune CPU and memory in all manifests based on observed performance and load.
* **Horizontal Pod Autoscaling (HPA):** Configure for stateless services (Nginx, Python APIs) if needed.
* **Monitoring & Logging:** Integrate with cluster-wide monitoring (e.g., Prometheus, Grafana) and logging solutions (e.g., EFK, Loki).
* **Backup Strategy:** Implement robust backups for PostgreSQL data and other critical persistent data.
* **Security Contexts & Network Policies:** Continuously review and refine. Implement Kubernetes NetworkPolicies to restrict pod-to-pod communication to only what's necessary.
* **Image Security:** Regularly scan your custom Docker images for vulnerabilities.
* **Secrets Management:** Consider more advanced secrets management solutions like HashiCorp Vault or cloud provider KMS for production.
