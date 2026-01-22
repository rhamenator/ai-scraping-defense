# AI Scraping Defense Stack

This system combats scraping by unauthorized AI bots targeting FOSS or documentation sites. It employs a multi-layered defense strategy including real-time detection, tarpitting, honeypots, and behavioral analysis with optional AI/LLM integration for sophisticated threat assessment.

## Features

* **Edge Filtering (Nginx + Lua):** Real-time filtering based on User-Agent, headers, and IP blocklists. Includes rate limiting. [cite: 2004, 2098, 2109, 2115, 2117, updated]
* **IP Blocklisting (Redis + Nginx + AI Service):** Confirmed malicious IPs are added to a Redis set and blocked efficiently at the edge by Nginx. [cite: updated]
* **Tarpit API (FastAPI):** Slow responses and dynamic fake content endpoints to waste bot resources and time. [cite: 2098, 2105, 2111, 2116, 2139, 2207, 2211, updated]
* **Escalation Engine (FastAPI):** Processes suspicious requests, applies heuristic scoring (including frequency analysis), uses a trained Random Forest model, and can trigger further analysis (e.g., via local LLM or external APIs). [cite: 2098, 2109, 2116, 2129, 2140, updated]
* **AI Service (FastAPI):** Receives escalation webhooks, manages the Redis blocklist, and handles configurable alerting (Slack, SMTP, Webhook). [cite: new/updated]
* **Admin UI (FastAPI):** Real-time metrics dashboard visualizing honeypot hits, escalations, and system activity. [cite: 2098, 2116, 2123]
* **Email Entropy Analysis:** Scores email addresses during registration to detect potentially bot-generated accounts (utility script provided). [cite: 2098, 2130]
* **JavaScript ZIP Honeypots:** Dynamically generated and rotated ZIP archives containing decoy JavaScript files to trap bots attempting to download assets. [cite: 2098, 2118, 2120]
* **Markov Fake Content Generator:** Creates plausible-looking but nonsensical text for fake documentation pages served by the tarpit. [cite: 2098, 2121]
* **ML Model Training:** Includes scripts to parse logs, label data (using heuristics and feedback logs), extract features (including frequency), and train a Random Forest classifier. [cite: new/updated]
* **GoAccess Analytics:** Configured to parse NGINX logs for traffic insights (optional setup). [cite: 2098]
* **Dockerized Stack:** Entire system orchestrated using Docker Compose for ease of deployment and scalability. Includes resource limits and basic healthchecks. [cite: 2098, 2105, updated]
* **Secrets Management:** Supports Docker secrets for sensitive configuration like API keys and passwords. [cite: new/updated]

## Getting Started

### See [`docs/getting_started.md`](docs/getting_started.md) for detailed instructions

### Prerequisites

* Docker
* Docker Compose

### Installation & Launch

1. **Clone the repository:**

    ```bash
    git clone [https://github.com/rhamenator/ai-scraping-defense.git](https://github.com/rhamenator/ai-scraping-defense.git)
    cd ai-scraping-defense
    ```

2. **Configure Environment:**
    * Copy `sample.env` to `.env` and customize settings (Webhook URLs, LLM endpoints, alert details, etc.).

        ```bash
        cp sample.env .env
        # Edit .env with your settings
        ```

    * Create `./secrets/` directory and place files containing sensitive values (e.g., `./secrets/smtp_password.txt`). **Add `secrets/` to `.gitignore`!**
3. **Build and Run:**

    ```bash
    docker-compose build
    docker-compose up -d
    ```

### Accessing Services (Default Ports)

* **Main Website / Docs:** `https://localhost/`
* **Tarpit Endpoint (Internal):** Accessed via Nginx redirect (`/api/tarpit`)
* **Admin UI:** `https://localhost/admin/`
* **Metrics API:** `https://localhost/admin/metrics` (used by Admin UI frontend)
* **GoAccess Dashboard (if enabled):** `https://localhost:7890`

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for a detailed diagram and component overview.

## Contributing

Contributions are welcome! Please see [`CONTRIBUTING.md`](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the terms of the GPL-3.0 license. See [`LICENSE`](../../LICENSE) for the full text and [License Summary](../../license_summary.md) for a summary.

## Security

Please report any security vulnerabilities according to the policy outlined in [`SECURITY.md`](SECURITY.md).

## Ethics & Usage

This system is intended for defensive purposes only. Use responsibly and ethically. Ensure compliance with relevant laws and regulations in your jurisdiction. See [`docs/legal_compliance.md`](docs/legal_compliance.md) and [`docs/privacy_policy.md`](docs/privacy_policy.md).
