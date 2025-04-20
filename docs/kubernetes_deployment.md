# Kubernetes Deployment Guide

This guide provides instructions for deploying the AI Scraping Defense Stack using the provided Kubernetes manifests. This method is generally recommended for production environments or scenarios requiring high availability and scalability.

For simpler setups or development environments, please refer to the [Docker Compose Guide](getting_started.md).

## Prerequisites

* **Kubernetes Cluster:** Access to a running Kubernetes cluster (e.g., Minikube, Kind, Docker Desktop K8s, EKS, GKE, AKS).
* **`kubectl`:** The Kubernetes command-line tool, configured to communicate with your cluster. ([Install kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl/)).
* **Storage Provisioner:** Your cluster must have a default `StorageClass` configured or you need to specify an appropriate `storageClassName` in the `PersistentVolumeClaim` definitions for Redis, Archives, and Models storage.
* **Container Registry:** A place to push your built Docker images (e.g., Docker Hub, GHCR, AWS ECR, Google GCR) that your Kubernetes cluster can access.
* **(Optional) Kustomize:** Useful for managing configuration variations between environments. ([Install Kustomize](https://kubectl.docs.kubernetes.io/installation/kustomize/)).
* **(Optional) Helm:** An alternative package manager for Kubernetes. (Helm charts are not provided in this guide but could be created).
* **(Optional) OpenSSL:** Needed to generate `dhparam.pem` if you haven't already.

## Repository Structure

The Kubernetes manifests are located in the `/kubernetes` directory:

```
kubernetes/
├── redis-statefulset.yaml
├── secrets.yaml           # Structure definition ONLY
├── configmap.yaml         # Common non-sensitive config
├── admin-ui-deployment.yaml
├── archive-rotator-deployment.yaml
├── tarpit-api-deployment.yaml
├── escalation-engine-deployment.yaml
├── ai-service-deployment.yaml
└── nginx-deployment.yaml    # Includes Nginx config, Lua, DHParam configmaps  
```

You will also need to create `PersistentVolumeClaim` definitions separately if required by your storage setup.

## Configuration Steps

### 1. Namespace (Recommended)

It's highly recommended to deploy the stack into its own namespace for better isolation.

```bash
kubectl create namespace ai-defense
```

If you create a namespace, add namespace: ai-defense to the metadata: section of *all* Kubernetes objects (Secrets, ConfigMaps, Services, Deployments, StatefulSets, PVCs) before applying them, or use the -n ai-defense flag with kubectl apply.

### **2. Secrets Creation (Mandatory)**

The kubernetes/secrets.yaml file defines the *structure* of the secrets the application expects, but **you must create the actual secrets** with your sensitive data. **Do not commit real secrets to Git.**

Replace placeholders like WU9V... with the base64-encoded versions of your actual secrets. Use echo -n 'YOUR_SECRET_VALUE' | base64 to encode.

**Methods:**

* **Option A: Edit kubernetes/secrets.yaml (Not Recommended for Git):**  
  * Edit the kubernetes/secrets.yaml file.  
  * Replace the placeholder base64 strings in the data fields with your *actual* base64-encoded secrets.  
  * Apply the file: kubectl apply -f kubernetes/secrets.yaml [-n ai-defense]  
  * **Warning:** Be extremely careful not to commit this file with real secrets.  
* **Option B: Use kubectl create secret generic (Recommended):**  
  * Create each secret individually using kubectl. Replace <YOUR_VALUE> with your actual secret.

#### Example for SMTP Password  

kubectl create secret generic smtp-credentials
  --from-literal=smtp_password='<YOUR_SMTP_PASSWORD>'
  [-n ai-defense]

#### Example for External API Key  

kubectl create secret generic external-api-credentials
  --from-literal=external_api_key='<YOUR_EXTERNAL_API_KEY>'
  [-n ai-defense]

#### Example for IP Reputation API Key  

kubectl create secret generic ip-reputation-credentials
  --from-literal=ip_reputation_api_key='<YOUR_IP_REPUTATION_API_KEY>'
  [-n ai-defense]

#### Example for Community Blocklist API Key  

kubectl create secret generic community-blocklist-credentials
  --from-literal=community_blocklist_api_key='<YOUR_COMMUNITY_BLOCKLIST_API_KEY>'
  [-n ai-defense]

#### Example for TLS Certificate/Key (if managing TLS in cluster)  

kubectl create secret tls tls-secret
  --cert=path/to/your.crt
  --key=path/to/your.key
  [-n ai-defense]

### **3. Persistent Volume Claims (PVCs) (Mandatory)**

The stack requires persistent storage for Redis data, shared archives, and ML models. Create PVC manifests based on your cluster's storage capabilities.

* **redis-data**: Handled automatically by the volumeClaimTemplates in redis-statefulset.yaml. Ensure a default StorageClass exists or modify the template.  
* **archives-pvc**: Needs to be created manually. This volume should support ReadWriteMany if you scale Nginx beyond one replica and it needs to serve archives directly, otherwise ReadWriteOnce (mounted by the single rotator pod) might suffice if Nginx reads via a shared filesystem mechanism provided by the volume type.  
* **models-pvc**: Needs to be created manually. Usually ReadOnlyMany (mounted by multiple escalation-engine pods) or ReadWriteOnce (if updated via a Job) is sufficient. You must place your trained bot_detection_rf_model.joblib file onto this volume after it's provisioned.

**Example archives-pvc.yaml (adjust size and storageClassName):**

#### kubernetes/archives-pvc.yaml  

apiVersion: v1  
kind: PersistentVolumeClaim  
metadata:  
  name: archives-pvc  

#### namespace: ai-defense  

spec:  
  accessModes:  
    # - ReadWriteMany # If multiple Nginx pods need write (unlikely)  
    - ReadWriteOnce # Sufficient if only rotator writes  
    # - ReadOnlyMany # If Nginx only reads and rotator handles writes elsewhere  
  resources:  
    requests:  
      storage: 5Gi # Adjust size as needed  

#### storageClassName: your-rwm-or-rwo-storage-class # Specify if needed

**Example models-pvc.yaml (adjust size and storageClassName):**

#### kubernetes/models-pvc.yaml  

apiVersion: v1  
kind: PersistentVolumeClaim  
metadata:  
  name: models-pvc  

#### namespace: ai-defense  

spec:  
  accessModes:  
    - ReadOnlyMany # Allow multiple escalation pods to read  
  resources:  
    requests:  
      storage: 1Gi # Adjust size  

#### storageClassName: your-rom-or-rwo-storage-class

Apply these PVCs: kubectl apply -f kubernetes/archives-pvc.yaml [-n ai-defense] etc. Then ensure the required data (like the model file) is populated.

### **4. Configuration Customization (ConfigMaps)**

* **kubernetes/configmap.yaml**: Defines common non-sensitive settings. You can modify this file directly before applying or use Kustomize/Helm overlays for environment-specific changes (e.g., different ALERT_METHOD defaults).  
* **kubernetes/nginx-deployment.yaml**:  
  * Paste your final nginx.conf content into the nginx-config ConfigMap definition within this file.  
  * Paste your final Lua scripts (check_blocklist.lua, detect_bot.lua) into the nginx-config ConfigMap definition.  
  * Generate DH parameters (openssl dhparam -out dhparam.pem 4096) and paste the content into the dhparam-config ConfigMap definition.

### **5. Image Preparation (Mandatory)**

* **Build Images:** Build the Docker images required by the deployments using your Dockerfile. You will need at least one image for the Python services (defense_stack_py_base in the examples) and one for Nginx (your-repo/ai-defense-stack-nginx placeholder used). Ensure the application code and dependencies are correctly included.  

  #### Example for Python base (adjust tag)  

  docker build -t myregistry/ai-defense-stack-base:v1.0 -f Dockerfile . --target python_base_stage # Assumes multi-stage Dockerfile  

  #### Example for Nginx (adjust tag)  

  docker build -t myregistry/ai-defense-stack-nginx:v1.0 -f Dockerfile . --target nginx_stage # Assumes multi-stage Dockerfile

* **Push Images:** Push the built images to a container registry accessible by your Kubernetes cluster.  
  docker push myregistry/ai-defense-stack-base:v1.0  
  docker push myregistry/ai-defense-stack-nginx:v1.0

* **Update Manifests:** Edit the image: fields in all Deployment and StatefulSet YAML files (kubernetes/*-deployment.yaml, kubernetes/redis-statefulset.yaml) to point to the images you just pushed.

## **Deployment**

Once all prerequisites, Secrets, PVCs, ConfigMaps, and image names are correctly configured:

### Apply all manifests in the kubernetes directory  

kubectl apply -f kubernetes/ [-n ai-defense]

### Or, if using Kustomize  

``` terminal
kustomize build <path_to_kustomize_dir> | kubectl apply -f - [-n ai-defense]
```

## **Verification**

* **Check Pod Status:**  
  kubectl get pods [-n ai-defense] -w # Watch status changes

  Wait for all pods to reach the Running state. Check for CrashLoopBackOff or Error statuses.  
* **Check Service Status:**  
  kubectl get svc [-n ai-defense]

  Note the CLUSTER-IP for internal services and the EXTERNAL-IP for the nginx service (if type LoadBalancer and supported by your environment).  
* **Check Logs:**  
  kubectl logs deploy/\<deployment-name\> [-n ai-defense] # e.g., kubectl logs deploy/escalation-engine  
  kubectl logs statefulset/redis [-n ai-defense]  
  kubectl logs \<pod-name\> [-n ai-defense] # For specific pod logs

  Look for successful startup messages and check for errors.

## **Accessing Services**

* **Main Application / Admin UI:** Access the application via the external IP address or hostname assigned to the nginx service (type LoadBalancer) or configured via an Ingress controller. The Admin UI will be available at http(s)://\<nginx-external-ip-or-hostname\>/admin/.  
* **Internal Services:** Services like redis, tarpit-api, escalation-engine, etc., are typically type ClusterIP and only accessible *within* the Kubernetes cluster using their service names (e.g., <http://escalation-engine:8003>).

## **Scaling**

To scale a service (e.g., the escalation engine):

kubectl scale deployment escalation-engine --replicas=3 [-n ai-defense]

## **Updates**

To update a service (e.g., deploy a new image version):

1. Update the image: tag in the corresponding Deployment YAML file.  
2. Apply the updated manifest: kubectl apply -f kubernetes/<service-deployment.yaml> [-n ai-defense]  
   Kubernetes will perform a rolling update by default.

## **Production Considerations (Kubernetes Specific)**

* **Namespaces:** Use dedicated namespaces for isolation.  
* **Resource Requests/Limits:** Tune CPU/Memory requests and limits based on observed performance and cluster capacity. Set requests appropriately for scheduling.  
* **Secrets Management:** Use robust secret management (Vault, cloud provider KMS/Secrets Manager) integrated via CSI drivers or external secrets operators instead of manual kubectl create secret.  
* **Storage:** Use appropriate StorageClass definitions for production workloads. Ensure backups for Persistent Volumes.  
* **Ingress:** Use an Ingress controller (like Nginx Ingress, Traefik) instead of Service type LoadBalancer for more flexible routing, path-based rules, and centralized TLS termination.  
* **Network Policies:** Implement
