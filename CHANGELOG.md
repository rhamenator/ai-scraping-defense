# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## **[0.0.5] - 2025-05-25**

### **Added**

* **Kubernetes PostgreSQL Schema Initialization:** Implemented automatic schema initialization for PostgreSQL in Kubernetes by mounting db/init_markov.sql via a new postgres-init-script-cm ConfigMap into the standard /docker-entrypoint-initdb.d/ directory of the PostgreSQL container. This removes the need for manual schema setup in Kubernetes.  
* **Helper Script for Local Setup:** Added setup_local_dirs.sh to assist users in creating the necessary local directory structure and placeholder secret files.

### **Changed**

* **Nginx robots.txt Handling (Docker Compose):** Updated nginx/lua/detect_bot.lua (for Docker Compose deployments) to dynamically load and parse robots.txt rules from the mounted /etc/nginx/robots.txt file, ensuring consistent behavior with Kubernetes for benign bot rule checking.  
* **Kubernetes SYSTEM_SEED Management:**  
  * Moved SYSTEM_SEED from kubernetes/configmap.yaml to kubernetes/secrets.yaml (under a new system-seed-secret) for enhanced security.  
  * Updated kubernetes/tarpit-api-deployment.yaml to source the SYSTEM_SEED environment variable from this new Secret.  
* **Kubernetes Image Placeholders:** Standardized placeholder image names (e.g., your-registry/ai-defense-python-base:latest, your-registry/ai-defense-nginx:latest) across all relevant Kubernetes YAML files (*-deployment.yaml,*-cronjob.yaml) to clarify where user-specific image URIs should be inserted.  
* **Documentation (mkdocs.yml):** Corrected the "License Summary" link in nav section to point to license_summary.md.  
* **Documentation (docs/api_references.md):** Updated to include the /metrics endpoint for the Escalation Engine.  
* **Documentation (docs/kubernetes_deployment.md):** Significantly updated to reflect the new PostgreSQL schema initialization method, SYSTEM_SEED relocation, standardized image placeholders, and other recent enhancements for clarity and accuracy.

### **Fixed**

* Ensured init_markov.sql script within kubernetes/postgres-init-script-cm.yaml correctly handles potential pre-existing markov_words ID 1 for the empty string token.

## **[0.0.4] - 2025-05-25**

### **Added**

* **Dynamic Wikipedia Corpus Generation:**  
  * Introduced util/corpus_wikipedia_updater.py script to periodically fetch content from random Wikipedia pages.  
  * Added kubernetes/corpus-updater-cronjob.yaml to schedule the corpus_wikipedia_updater.py script.  
  * Added kubernetes/corpus-pvc.yaml to define a PersistentVolumeClaim (corpus-data-pvc) for storing the dynamically generated corpus.  
* **Dynamic robots.txt Management:**  
  * Introduced util/robots_fetcher.py script to periodically fetch robots.txt from the REAL_BACKEND_HOST.  
  * Added kubernetes/robots-fetcher-cronjob.yaml (or robots-fetcher-setup.yaml) defining a ServiceAccount (robots-fetcher-sa), Role (configmap-updater-role), RoleBinding, and a CronJob (robots-txt-fetcher) to run the script and update a live-robots-txt-config ConfigMap.  
* **Persistent Storage for Models and Archives:**  
  * Added kubernetes/models-pvc.yaml for models-pvc to store trained ML models.  
  * Added kubernetes/archives-pvc.yaml for archives-pvc to store generated ZIP honeypot archives.  
* **Kubernetes Security Hardening:**  
  * Applied securityContext (e.g., runAsNonRoot, runAsUser, capabilities: {drop: ["ALL"]}) to Pod and container specifications in Deployments, StatefulSets, and CronJob templates for enhanced security.  
  * Restricted permissions for the robots-fetcher-sa ServiceAccount's Role to only manage the specific live-robots-txt-config ConfigMap.  
* **New Python Dependencies:** Added kubernetes, wikipedia-api, beautifulsoup4, lxml to requirements.txt for the new utility scripts.

### **Changed**

* **Kubernetes Manifests:**  
  * Applied namespace: ai-defense consistently across all Kubernetes resource manifests for better isolation and organization.  
  * Updated service endpoint configurations in kubernetes/configmap.yaml (app-config) to use Fully Qualified Domain Names (FQDNs) for robust intra-cluster communication (e.g., redis.ai-defense.svc.cluster.local).  
  * Updated kubernetes/nginx-deployment.yaml:  
    * Nginx configuration and detect_bot.lua now utilize the dynamically fetched robots.txt (mounted from the live-robots-txt-config ConfigMap).  
  * Updated kubernetes/escalation-engine-deployment.yaml to mount and use the live-robots-txt-config ConfigMap for its TRAINING_ROBOTS_TXT_PATH.  
  * Converted the one-time Markov training Kubernetes Job to a periodic CronJob in kubernetes/markov-model-trainer.yaml, configured to read the corpus from corpus-data-pvc.  
  * Refined filenames for Kubernetes CronJob YAMLs for clarity (e.g., robots-fetcher-cronjob.yaml for the robots.txt fetcher setup, markov-model-trainer.yaml for the Markov training CronJob).  
* **Nginx Lua Scripts:**  
  * Corrected nginx/lua/check_blocklist.lua to use redis:exists() for checking individual IP keys (e.g., blocklist:ip:1.2.3.4) in Redis, aligning with how blocklist entries are stored.  
* **Dockerfile:**  
  * Updated to include the new util/ directory (containing robots_fetcher.py and corpus_wikipedia_updater.py) in the Docker image.  
* **docker-compose.yml:**  
  * Enhanced for local development by adding ./data:/app/data and ./util:/app/util volume mounts to Python services, facilitating easier testing of new utility scripts.  
* **Documentation:**  
  * Updated README.md (Features section).  
  * Updated docs/architecture.md (Component Overview, Data Flow, and Mermaid diagram).  
  * Updated docs/key_data_flows.md.  
  * Substantially updated docs/kubernetes_deployment.md to reflect new resources, namespacing, security contexts, and deployment procedures.

### **Fixed**

* Resolved potential inconsistencies in ServiceAccount naming and RoleBinding references for the robots-fetcher CronJob.  
* Ensured PVCs referenced by CronJobs and Deployments are correctly configured to be in the ai-defense namespace.

## [0.0.3] - 2025-04-22

### Added

* **PostgreSQL Markov Backend:** Tarpit content generation now uses Markov chains stored in PostgreSQL for persistence and scalability.
* **PostgreSQL Training Script:** New script (`rag/train_markov_postgres.py`) to populate the Markov database from a text corpus.
* **Tarpit Hop Limit:** Configurable limit (`TAR_PIT_MAX_HOPS`, `TAR_PIT_HOP_WINDOW_SECONDS`) on tarpit requests per IP, tracked in Redis (`REDIS_DB_TAR_PIT_HOPS`). Exceeding limit triggers IP block.
* **Deterministic Tarpit Generation:** Tarpit pages and links are now generated deterministically based on URL hash and system seed (`SYSTEM_SEED`), creating a stable fake site structure.
* **Example Kubernetes PostgreSQL Manifest:** Added `kubernetes/postgres-statefulset.yaml` as an example deployment.
* **Example Main Website Nginx Config:** Added `example_main_website_nginx.conf` to illustrate proxying to the anti_scrape stack.
* **Configurable JSON Metrics Logging:** Added option (`LOG_METRICS_TO_JSON`) to periodically dump metrics to a JSON file for debugging.
* **PostgreSQL Dependency:** Added `psycopg2-binary` to `requirements.txt`.

### Changed

* **Nginx `robots.txt` Handling:** Updated `nginx/lua/detect_bot.lua` to check `robots.txt` rules (simplified list) for known benign bots before allowing or tarpitting.
* **Nginx Configuration for Separate Deployment:** Modified `nginx/nginx.conf` to proxy allowed traffic to a backend defined by `REAL_BACKEND_HOST` environment variable.
* **Tarpit Content Generation:** Replaced `markovify` logic with PostgreSQL queries in `tarpit/markov_generator.py`.
* **Configuration Files:** Updated `docker-compose.yml` and `kubernetes/configmap.yaml` with new environment variables for PostgreSQL, Tarpit hop limit, and corrected names.
* **Tarpit API (`tarpit_api.py`):** Integrated hop limit check logic, Redis connections for hops and blocklist, and deterministic seeding.

### Fixed

* **Environment Variable Naming:** Corrected environment variable names containing "TAR PIT" to use underscores (e.g., `TAR_PIT_MAX_HOPS`).

### Added in 0.0.2 - 2025-04-20

* Kubernetes manifests (`/kubernetes`) for deploying services, including ConfigMaps, Secrets structure, Deployments, StatefulSet (Redis), and Services.
* Initial structure for NGINX reverse proxy with Lua support.
* FastAPI service skeleton for tarpit (`/tarpit`).

### Added in 0.0.1 - 2025-04-19

* Initial structure for NGINX reverse proxy with Lua support.
* FastAPI service skeleton for tarpit (`/tarpit`).
* FastAPI service skeleton for escalation engine (`/escalate`).
* Flask service skeleton for Admin UI (`/admin`, `/metrics`).
* Basic `metrics.py` module for in-memory stats tracking.
* Python script placeholders for Markov generator, JS ZIP generator, email entropy scanner, webhook forwarder.
* Docker Compose setup for multi-container orchestration.
* Base `Dockerfile` with core dependencies.
* `README.md`, `LICENSE` (GPL-3.0), `LICENSE.md`, `CONTRIBUTING.md`, `SECURITY.md`.
* `.gitignore` file.
* GitHub Actions CI workflow (`ci.yml`) and PR labeler (`labeler.yml`).
* Issue and Pull Request templates (`.github/`).
* Documentation structure (`/docs`) with placeholders for architecture, API reference, legal info.
* Synthetic corpus generator (`synthetic_data_generator.py`).
* Wikipedia random page scraper (`wiki_scraper_generator.py`).
* Slow streaming HTML response logic in tarpit API.
* Rotating archive logic for JS honeypots.
* Webhook integration in escalation engine.
* Fake page generation with Markov text and randomized links.
* Admin UI template (`admin_ui/templates/index.html`).
* GoAccess configuration (`goaccess/goaccess.conf`).
* Redis-based IP blocklisting checked by Nginx/Lua (`check_blocklist.lua`).
* AI Service (`ai_webhook.py`) to receive webhooks, manage blocklist, and send alerts (Slack, SMTP, Webhook).
* Redis-based frequency tracking in Escalation Engine.
* Random Forest model training script (`rag/training.py`) using log data, feedback, and feature extraction.
* Support for Docker secrets for sensitive configuration.
* Enhanced logging using Python's `logging` module in backend services.
* Basic health check endpoints for backend services.
* Resource limits and basic healthcheck in `docker-compose.yml`.
* Recommended security headers in `nginx.conf`.
* Detailed "Production Considerations" section in `docs/getting_started.md`.
* `sample.env` file.

### Changed

* Refined escalation pipeline logic (heuristic -> RF model -> local LLM -> external API -> webhook).
* Improved honeypot field obfuscation using dynamic generation and realistic naming.
* Made tarpit response streaming more robust and randomized delay.
* Switched Markov generator corpus source from Wikipedia scraping to synthetic data, then back to optional Wikipedia scraping based on user preference.
* Refined directory structure for clarity (e.g., separating services).
* Updated `docker-compose.yml` to include all services, networks, volumes, secrets, and resource limits.
* Enhanced Nginx Lua bot detection (`detect_bot.lua`) with more header checks and scoring logic.
* Improved error handling and logging in backend Python services.
* Updated `nginx.conf` with security headers, refined rate limits, and HTTPS placeholders.
* Renamed `nginx.conf.txt` to `nginx.conf`.

### Fixed

* Corrected placeholder count mismatch in JS template generator.
* Fixed file path issues for Windows compatibility during testing.
* Removed emojis from README for better PDF compatibility.
* Ensured consistent timestamp handling (UTC ISO format) across services.
* Improved robustness of Redis connections and operations.

## [0.0.0] - 2025-04-18

### Added

* Initial stable release of the AI Scraping Defense Stack.
* Core functionality: NGINX/Lua detection, Tarpit API, Basic Escalation, Admin Metrics UI.
* Documentation V1.
