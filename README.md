# AI Scraping Defense Stack

This system combats scraping by unauthorized AI bots targeting FOSS or documentation sites. It employs a multi-layered defense strategy including real-time detection, tarpitting, honeypots, and behavioral analysis with optional AI/LLM integration for sophisticated threat assessment.

## Features

* **Edge Filtering (Nginx + Lua):** Real-time filtering based on User-Agent, headers, and IP blocklists. Includes rate limiting.
* **IP Blocklisting (Redis + Nginx + AI Service):** Confirmed malicious IPs are added to a Redis set and blocked efficiently at the edge by Nginx.
* **Tarpit API (FastAPI):** Slow responses and dynamic fake content endpoints to waste bot resources and time.
* **Escalation Engine (FastAPI):** Processes suspicious requests, applies heuristic scoring (including frequency analysis), uses a trained Random Forest model, optionally checks **IP reputation** (configurable), and can trigger further analysis (e.g., via local LLM or external APIs). Includes hooks for potential **CAPTCHA challenges** (configurable).
* **AI Service (FastAPI):** Receives escalation webhooks, manages the Redis blocklist, optionally reports blocked IPs to **community blocklists** (configurable), and handles configurable alerting (Slack, SMTP, Webhook).
* **Admin UI (Flask):** Real-time metrics dashboard visualizing honeypot hits, escalations, and system activity.
* **Email Entropy Analysis:** Scores email addresses during registration to detect potentially bot-generated accounts (utility script provided).
* **JavaScript ZIP Honeypots:** Dynamically generated and rotated ZIP archives containing decoy JavaScript files to trap bots attempting to download assets.
* **Markov Fake Content Generator:** Creates plausible-looking but nonsensical text for fake documentation pages served by the tarpit.
* **ML Model Training:** Includes scripts to parse logs, label data (using heuristics and feedback logs), extract features (including frequency), and train a Random Forest classifier.
* **GoAccess Analytics:** Configured to parse NGINX logs for traffic insights (optional setup).
* **Dockerized Stack:** Entire system orchestrated using Docker Compose for ease of deployment and scalability. Includes resource limits and basic healthchecks.
* **Secrets Management:** Supports Docker secrets for sensitive configuration like API keys and passwords.
* **Configurable Integrations:** Key external interactions like IP reputation checks, community blocklist reporting, and CAPTCHA triggers are configurable via environment variables.

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

This project is licensed under the terms of the GPL-3.0 license. See [`LICENSE`](LICENSE) for the full text and [`LICENSE.md`](LICENSE.md) for a summary.

## Security

Please report any security vulnerabilities according to the policy outlined in [`SECURITY.md`](SECURITY.md).

## Ethics & Usage

This system is intended for defensive purposes only. Use responsibly and ethically. Ensure compliance with relevant laws and regulations in your jurisdiction. See [`docs/legal_compliance.md`](docs/legal_compliance.md) and [`docs/privacy_policy.md`](docs/privacy_policy.md).
