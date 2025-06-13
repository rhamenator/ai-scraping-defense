# AI Scraping Defense Stack

## *This system is a work-in-progress and not yet ready for release*

This system combats scraping by unauthorized AI bots targeting FOSS or documentation sites. It employs a multi-layered defense strategy including real-time detection, tarpitting, honeypots, and behavioral analysis with optional AI/LLM integration for sophisticated threat assessment.

## Features

This project employs a multi-layered defense strategy:

* **Edge Filtering (Nginx + Lua):** Real-time filtering based on User-Agent, headers, and IP blocklists. Includes rate limiting. The Lua scripts now use a dynamically updated `robots.txt` (fetched periodically from the protected backend) to check compliance for known benign bots.
* **IP Blocklisting (Redis + Nginx + AI Service):** Confirmed malicious IPs (identified by various system components) are added as individual keys with TTLs to a Redis database (DB 2) and blocked efficiently at the edge by Nginx.
* **Tarpit API (FastAPI + PostgreSQL):**
  * Serves endlessly deep, slow-streaming fake content pages to waste bot resources.
  * Uses **PostgreSQL-backed Markov chains** for persistent and scalable fake text generation. The corpus for this is now **dynamically updated periodically by fetching content from Wikipedia**.
  * Generates **deterministic content and links** based on URL hash and a system seed, creating a stable maze.
  * Implements a **configurable hop limit** tracked per IP in Redis (DB 4) to prevent excessive resource use, blocking IPs that exceed the limit.
* **Escalation Engine (FastAPI):** Processes suspicious requests redirected from the Tarpit or Nginx. Applies heuristic scoring (including frequency analysis via Redis DB 3), uses a trained Random Forest model, optionally checks **IP reputation** (configurable), and can trigger further analysis (e.g., via local LLM or external APIs). It now also uses the dynamically updated `robots.txt` for its logic.
* **AI Service (FastAPI):** Receives escalation webhooks, manages the Redis blocklist (DB 2), optionally reports blocked IPs to **community blocklists** (configurable), and handles configurable alerting (Slack, SMTP, Webhook).
* **Admin UI (Flask):** Real-time metrics dashboard visualizing system activity.
* **Dynamic `robots.txt` Management:** A Kubernetes CronJob (`robots-fetcher-cronjob.yaml`) periodically fetches `robots.txt` from the `REAL_BACKEND_HOST`, storing it in a ConfigMap (`live-robots-txt-config`) for use by Nginx and other services.
* **Dynamic Wikipedia Corpus Generation:** A Kubernetes CronJob (`corpus-updater-cronjob.yaml`) periodically fetches content from Wikipedia, saving it to a PersistentVolumeClaim (`corpus-data-pvc`).
* **PostgreSQL Markov Training (Automated):** A Kubernetes CronJob (`markov-model-trainer.yaml`) periodically retrains the PostgreSQL Markov database using the dynamically updated corpus from the PVC.
* **Kubernetes Deployment:**
  * Comprehensive Kubernetes manifests provided for deploying the entire stack.
  * All resources are deployed into a dedicated namespace (default: `ai-defense`).
  * Utilizes `PersistentVolumeClaims` for corpus data (`corpus-data-pvc`), ML models (`models-pvc`), and ZIP archives (`archives-pvc`).
  * Includes `securityContext` settings for Deployments, StatefulSets, and CronJobs to enhance security by adhering to the principle of least privilege.
  * RBAC is configured for CronJobs needing to interact with Kubernetes resources (e.g., the `robots.txt` fetcher updating a ConfigMap).
* **Email Entropy Analysis:** Utility script (`rag/email_entropy_scanner.py`) to score email addresses for detecting potentially bot-generated accounts.
* **JavaScript ZIP Honeypots:** Dynamically generated and rotated ZIP archives (`archive-rotator-deployment.yaml`) containing decoy JavaScript files.
* **ML Model Training:** Includes scripts (`rag/training.py`) to parse logs, label data, extract features, and train a Random Forest classifier.
* **Dockerized Stack:** Entire system orchestrated using Docker Compose for local development and testing.
* **Secrets Management:** Supports Docker secrets and Kubernetes Secrets for sensitive configurations.
* **Separate Deployment Ready:** Nginx configuration supports running the anti-scrape stack separately from the protected web application using `REAL_BACKEND_HOST`.

## Getting Started

### See [docs/getting_started.md](docs/getting_started.md) for detailed instructions using Docker Compose

### For Kubernetes deployments, see [docs/kubernetes_deployment.md](docs/kubernetes_deployment.md)

### Accessing Services (Default Ports)

*(Note: Ports might differ in Kubernetes depending on Service type and Ingress configuration)*

* **Main Website / Docs:** `http://localhost/` (or `https://localhost/` if HTTPS configured)
* **Tarpit Endpoint (Internal):** Accessed via Nginx redirect (`/api/tarpit`)
* **Admin UI:** `http://localhost/admin/` (or `https://localhost/admin/`)

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for a detailed diagram and component overview.

## Contributing

Contributions are welcome! Please see [`CONTRIBUTING.md`](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the terms of the GPL-3.0 license. See [`LICENSE`](LICENSE) for the full text and [`license_summary.md`](license_summary.md) for a summary.

## Security

Please report any security vulnerabilities according to the policy outlined in [`SECURITY.md`](SECURITY.md).

## Ethics & Usage

This system is intended for defensive purposes only. Use responsibly and ethically. Ensure compliance with relevant laws and regulations in your jurisdiction. See [`docs/legal_compliance.md`](docs/legal_compliance.md) and [`docs/privacy_policy.md`](docs/privacy_policy.md).
