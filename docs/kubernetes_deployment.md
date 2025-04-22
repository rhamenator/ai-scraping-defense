# Kubernetes Deployment Guide

This guide provides instructions for deploying the AI Scraping Defense Stack on a Kubernetes cluster using the provided manifest files located in the `/kubernetes` directory.

## 1. Prerequisites

* **Kubernetes Cluster:** Access to a functioning Kubernetes cluster (e.g., Minikube, Kind, K3s, managed cloud provider cluster like GKE, EKS, AKS).
* **`kubectl`:** The Kubernetes command-line tool, configured to interact with your cluster. ([Install kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl/))
* **Persistent Storage:** Your cluster must have a default StorageClass configured, or you need to define one and update the `PersistentVolumeClaim` definitions in `redis-statefulset.yaml` and `postgres-statefulset.yaml` to use it. Persistent storage is required for Redis and PostgreSQL data.
* **Docker Image Registry:** Container images for the stack need to be available to your cluster. You can:
  * Build the images locally and push them to a registry (like Docker Hub, GCR, ECR, etc.) accessible by your cluster. Update the `image:` fields in the Deployment/StatefulSet manifests accordingly.
  * If using a local cluster (Minikube, Kind), you might be able to build directly into the cluster's Docker daemon (e.g., `eval $(minikube docker-env)` before building).
* **Secrets:** Prepare secret values locally before creating Kubernetes Secrets (see Step 3).

## 2. Overview of Kubernetes Manifests

The `/kubernetes` directory contains YAML manifests for deploying each component:

* **`configmap.yaml`:** Defines non-sensitive configuration used by multiple services (Redis hosts, API endpoints, feature flags, default TTLs, **PostgreSQL config**, **Tarpit settings**, **System Seed**, **Backend Host**).
* **`secrets.yaml`:** Defines the structure for Kubernetes Secrets to hold sensitive data (API keys, passwords). You need to populate this with your actual base64-encoded secrets. Includes placeholders for SMTP, external APIs, **PostgreSQL**, and **Redis** passwords.
* **`redis-statefulset.yaml`:** Deploys Redis as a StatefulSet with persistent storage for caching blocklists, frequency data, tarpit flags, and **tarpit hop counts**. Includes a Service definition.
* **`postgres-statefulset.yaml`:** Deploys PostgreSQL as a StatefulSet with persistent storage for the **Markov chain database**. Includes Service definitions and requires a Secret for the password.
* **`*-deployment.yaml`:** Defines Deployments and Services for each microservice:
  * `nginx-deployment.yaml`
  * `tarpit-api-deployment.yaml`
  * `escalation-engine-deployment.yaml`
  * `ai-service-deployment.yaml`
  * `admin-ui-deployment.yaml`
  * `archive-rotator-deployment.yaml` (Consider running as a CronJob instead of Deployment if applicable)
* **(Optional) Namespace:** You might want to deploy the stack within a dedicated Kubernetes namespace (e.g., `ai-defense`). If so, create the namespace (`kubectl create namespace ai-defense`) and add `namespace: ai-defense` to the `metadata:` section of *all* manifest files.

## 3. Configuration Steps

1. **Prepare Secrets:**
    * **Identify Required Secrets:** Determine which secrets you need based on your configuration (SMTP password, API keys for external services, PostgreSQL password, optional Redis password).
    * **Encode Secrets:** For each secret value, encode it using base64. **Important:** Use `echo -n 'yoursecretvalue'` to avoid adding a newline character before encoding.

        ```bash
        echo -n 'your_secure_pg_password' | base64
        echo -n 'your_secure_redis_password' | base64 # If using Redis auth
        echo -n 'your_smtp_password' | base64
        echo -n 'your_external_api_key' | base64
        # ... etc.
        ```

    * **Edit `secrets.yaml`:** Open `kubernetes/secrets.yaml`. Replace the placeholder base64 strings (like `WU9V...`) in the `data:` section with your actual encoded secret values. Ensure the keys (`pg_password.txt`, `redis_password.txt`, `smtp_password.txt`, etc.) match those expected by the volume mounts in the Deployment/StatefulSet manifests.

2. **Review & Customize `configmap.yaml`:**
    * Open `kubernetes/configmap.yaml`.
    * **Crucially, set `SYSTEM_SEED`:** Change the default value to a unique, secure random string.
    * **Set `REAL_BACKEND_HOST`:** Define the internal Kubernetes service name or IP address and port of your actual web application that Nginx should proxy legitimate traffic to (e.g., `http://my-app-service.my-namespace:8080`).
    * **Review Tarpit Settings:** Adjust `TAR_PIT_MAX_HOPS`, `TAR_PIT_HOP_WINDOW_SECONDS`, delays, etc.
    * **Review Redis DBs:** Ensure the database numbers (`REDIS_DB_*`) do not conflict if sharing a Redis instance with other applications.
    * **Review PostgreSQL Config:** Ensure `PG_DBNAME` and `PG_USER` match the settings used when setting up the PostgreSQL database/credentials.
    * **Configure Alerting & External APIs:** Set URLs, enable/disable features (`ENABLE_IP_REPUTATION`, etc.) as needed. Note that sensitive keys for these are in `secrets.yaml`.
    * **Adjust Resource Paths:** Ensure paths like `TRAINING_MODEL_SAVE_PATH` are appropriate for the container environment (usually `/app/...`).

3. **Review StatefulSet Storage:**
    * Open `kubernetes/redis-statefulset.yaml` and `kubernetes/postgres-statefulset.yaml`.
    * Check the `volumeClaimTemplates.spec.storageClassName`. If your cluster doesn't have a default StorageClass or you need a specific one (e.g., for SSDs), uncomment and set the `storageClassName` field.
    * Adjust `volumeClaimTemplates.spec.resources.requests.storage` (e.g., `1Gi` for Redis, `10Gi` for PostgreSQL) based on your expected data volume.

4. **Build & Push Container Images:**
    * Build the Docker image defined in `Dockerfile` using the `docker build` command.
    * Tag the image appropriately for your container registry (e.g., `your-registry/ai-defense-stack:latest` or `your-registry/ai-defense-stack:v0.0.3`).
    * Push the image to your registry: `docker push your-registry/ai-defense-stack:tag`.
    * Update the `image:` field in all `*-deployment.yaml` files and `postgres-statefulset.yaml` / `redis-statefulset.yaml` to point to your pushed image tag.

## 4. Deployment Steps

1. **Apply Namespace (If using one):**

    ```bash
    kubectl create namespace ai-defense # Or your chosen namespace name
    ```

2. **Apply ConfigMap:**

    ```bash
    kubectl apply -f kubernetes/configmap.yaml [-n your-namespace]
    ```

3. **Apply Secrets:**

    ```bash
    kubectl apply -f kubernetes/secrets.yaml [-n your-namespace]
    ```

4. **Apply Redis StatefulSet & Service:**

    ```bash
    kubectl apply -f kubernetes/redis-statefulset.yaml [-n your-namespace]
    ```

    * Monitor its creation: `kubectl get pods -l app=redis -w [-n your-namespace]` (Wait for Running state)

5. **Apply PostgreSQL StatefulSet & Service:**

    ```bash
    kubectl apply -f kubernetes/postgres-statefulset.yaml [-n your-namespace]
    ```

    * Monitor its creation: `kubectl get pods -l app=postgres-markov -w [-n your-namespace]` (Wait for Running state)
    * **Schema Setup:** If you didn't mount an init script, you'll need to manually apply the schema (`db/init_markov.sql`) to the PostgreSQL pod *after* it's running. You can use `kubectl exec` to run `psql`.

6. **Apply Deployments & Services (Order generally doesn't strictly matter, but deploying dependencies first is good practice):**

    ```bash
    kubectl apply -f kubernetes/ai-service-deployment.yaml [-n your-namespace]
    kubectl apply -f kubernetes/escalation-engine-deployment.yaml [-n your-namespace]
    kubectl apply -f kubernetes/tarpit-api-deployment.yaml [-n your-namespace]
    kubectl apply -f kubernetes/admin-ui-deployment.yaml [-n your-namespace]
    kubectl apply -f kubernetes/archive-rotator-deployment.yaml [-n your-namespace] # Or create as CronJob
    kubectl apply -f kubernetes/nginx-deployment.yaml [-n your-namespace]
    ```

7. **Verify Pods:**

    ```bash
    kubectl get pods [-n your-namespace]
    ```

    * Ensure all pods transition to the `Running` state. Check logs for any startup errors using `kubectl logs <pod-name> [-n your-namespace]`.

8. **Train Markov Model (Required Job):**
    * The PostgreSQL database needs to be populated with Markov data. This should be done via a Kubernetes Job after the PostgreSQL StatefulSet is ready.
    * You will need to create a `kubernetes/markov-trainer-job.yaml` manifest. This Job would:
        * Use the same application image (`your-registry/ai-defense-stack:tag`).
        * Mount necessary ConfigMaps/Secrets (especially for PostgreSQL connection).
        * Mount your corpus text file(s) via a ConfigMap or PersistentVolume.
        * Run the command: `python rag/train_markov_postgres.py /path/to/corpus/inside/pod/your_corpus.txt`
    * **Example Job Snippet (Adapt as needed):**

        ```yaml
        apiVersion: batch/v1
        kind: Job
        metadata:
          name: markov-trainer
          # namespace: ai-defense
        spec:
          template:
            spec:
              containers:
              - name: markov-trainer
                image: your-registry/ai-defense-stack:tag # Use your image
                command: ["python", "rag/train_markov_postgres.py", "/app/data/corpus/your_corpus.txt"] # Adjust path
                envFrom: # Load environment variables for DB connection etc.
                - configMapRef:
                    name: app-config
                volumeMounts:
                - name: pg-secret
                  mountPath: /run/secrets/postgres
                  readOnly: true
                - name: corpus-data
                  mountPath: /app/data/corpus # Mount corpus file(s) here
              volumes:
              - name: pg-secret
                secret:
                  secretName: postgres-credentials
                  items:
                    - key: pg_password.txt
                      path: pg_password.txt
              - name: corpus-data # Define how corpus is provided (e.g., ConfigMap, PV)
                configMap:
                  name: corpus-text-configmap # Example: Corpus in a ConfigMap
              restartPolicy: Never # Jobs should run once
          backoffLimit: 2 # Retry job a few times on failure
        ```

    * Apply the Job: `kubectl apply -f kubernetes/markov-trainer-job.yaml [-n your-namespace]`
    * Monitor the Job: `kubectl get jobs [-n your-namespace]`, `kubectl logs job/markov-trainer [-n your-namespace]`

9. **Access Services:**
    * How you access the services (especially Nginx) depends on your cluster setup:
        * **LoadBalancer Service:** If the `nginx-service` type is `LoadBalancer`, find the external IP: `kubectl get svc nginx-service [-n your-namespace]`
        * **NodePort Service:** Access via `<NodeIP>:<NodePort>`. Find the NodePort: `kubectl get svc nginx-service [-n your-namespace]`
        * **Ingress:** Configure a Kubernetes Ingress resource pointing to the `nginx-service`. This is the recommended approach for production, allowing hostname-based routing, TLS termination, etc.

## 5. Testing & Verification

* Follow similar steps as in the Docker Compose guide (Section 5), but use the appropriate Kubernetes service address or Ingress hostname instead of `localhost`.
* Use `kubectl logs <pod-name>` to check logs for individual services.
* Use `kubectl exec -it <redis-pod-name> -- redis-cli -n <db_number>` to inspect Redis data.
* Use `kubectl exec -it <postgres-pod-name> -- psql -U <user> -d <db>` to inspect PostgreSQL data.

## 6. Production Considerations

* **Ingress:** Use an Ingress controller (like Nginx Ingress, Traefik) for robust routing, TLS termination, and hostname management.
* **Resource Requests/Limits:** Fine-tune CPU and memory requests/limits in Deployments/StatefulSets based on monitoring.
* **Horizontal Pod Autoscaling (HPA):** Configure HPAs for stateless services (Nginx, APIs) based on CPU or custom metrics.
* **Monitoring:** Integrate with Prometheus/Grafana or cloud provider monitoring tools.
* **Logging:** Deploy a cluster-wide logging solution (e.g., EFK, Loki).
* **StorageClass:** Choose an appropriate StorageClass for Redis and PostgreSQL persistent volumes.
* **Backups:** Implement robust backup strategies for PostgreSQL data and potentially Redis snapshots.
* **Security Contexts:** Define appropriate security contexts for pods (e.g., run as non-root).
* **Network Policies:** Use Kubernetes NetworkPolicies to restrict traffic flow between pods.
