# AI Scraping Defense Stack

This system combats scraping by unauthorized AI bots targeting FOSS or documentation sites. It employs a multi-layered defense strategy including real-time detection, tarpitting, honeypots, and behavioral analysis with optional AI/LLM integration for sophisticated threat assessment.

## Features

* **Edge Filtering (Nginx + Lua):** Real-time filtering based on User-Agent, headers, `robots.txt` compliance (for known benign bots), and IP blocklists. Includes rate limiting.
* **IP Blocklisting (Redis + Nginx + AI Service):** Confirmed malicious IPs are added to a Redis set (DB 2) and blocked efficiently at the edge by Nginx.
* **Tarpit API (FastAPI + PostgreSQL):**
  * Serves endlessly deep, slow-streaming fake content pages to waste bot resources.
  * Uses **PostgreSQL-backed Markov chains** for persistent and scalable fake text generation.
  * Generates **deterministic content and links** based on URL hash and system seed, creating a stable maze.
  * Implements a **configurable hop limit** tracked per IP in Redis (DB 4) to prevent excessive resource use, blocking IPs that exceed the limit.
* **Escalation Engine (FastAPI):** Processes suspicious requests, applies heuristic scoring (including frequency analysis via Redis DB 3), uses a trained Random Forest model, optionally checks **IP reputation** (configurable), and can trigger further analysis (e.g., via local LLM or external APIs). Includes hooks for potential **CAPTCHA challenges** (configurable).
* **AI Service (FastAPI):** Receives escalation webhooks, manages the Redis blocklist (DB 2), optionally reports blocked IPs to **community blocklists** (configurable), and handles configurable alerting (Slack, SMTP, Webhook).
* **Admin UI (Flask):** Real-time metrics dashboard visualizing honeypot hits, escalations, and system activity.
* **PostgreSQL Markov Training:** Includes script (`rag/train_markov_postgres.py`) to populate the PostgreSQL Markov database from a text corpus.
* **Email Entropy Analysis:** Scores email addresses during registration to detect potentially bot-generated accounts (utility script provided).
* **JavaScript ZIP Honeypots:** Dynamically generated and rotated ZIP archives containing decoy JavaScript files to trap bots attempting to download assets.
* **ML Model Training:** Includes scripts to parse logs, label data, extract features, and train a Random Forest classifier.
* **GoAccess Analytics:** Configured to parse NGINX logs for traffic insights (optional setup).
* **Dockerized Stack:** Entire system orchestrated using Docker Compose for ease of deployment and scalability. Includes resource limits and healthchecks.
* **Kubernetes Support:** Includes example manifests for Kubernetes deployment.
* **Secrets Management:** Supports Docker/Kubernetes secrets for sensitive configuration like API keys and passwords.
* **Configurable Integrations:** Key external interactions are configurable via environment variables.
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
