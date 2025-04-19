# AI Scraping Defense Stack

This system combats scraping by unauthorized AI bots targeting FOSS or documentation sites. It employs a multi-layered defense strategy including real-time detection, tarpitting, honeypots, and behavioral analysis with optional AI/LLM integration for sophisticated threat assessment.

## Features

- **Tarpit API:** Slow responses and fake content endpoints (FastAPI-based) to waste bot resources and time. [cite: 2098, 2105, 2111, 2116, 2139, 2207, 2211]
- **NGINX + Lua Detection:** Real-time filtering of requests based on User-Agent strings or other simple heuristics. [cite: 2004, 2098, 2109, 2115, 2117]
- **Escalation Engine:** Processes suspicious requests, applies heuristic scoring, and can trigger further analysis (e.g., via local LLM or external webhooks). [cite: 2098, 2109, 2116, 2129, 2140]
- **Admin UI:** Real-time metrics dashboard (Flask-based) visualizing honeypot hits, escalations, and system activity. [cite: 2098, 2116, 2123]
- **Email Entropy Analysis:** Scores email addresses during registration to detect potentially bot-generated accounts. [cite: 2098, 2130]
- **JavaScript ZIP Honeypots:** Dynamically generated and rotated ZIP archives containing decoy JavaScript files to trap bots attempting to download assets. [cite: 2098, 2118, 2120]
- **Markov Fake Content Generator:** Creates plausible-looking but nonsensical text for fake documentation pages served by the tarpit. [cite: 2098, 2121]
- **GoAccess Analytics:** Configured to parse NGINX logs for traffic insights (optional setup). [cite: 2098]
- **Webhook Integration:** Allows escalated events to trigger external actions (alerts, blocking via Fail2Ban/CrowdSec, custom analysis pipelines). [cite: 2098, 2130]
- **Dockerized Stack:** Entire system orchestrated using Docker Compose for ease of deployment and scalability. [cite: 2098, 2105]

## Getting Started

### See [`docs/getting_started.md`](docs/getting_started.md) for detailed instructions.

### Prerequisites

- Docker
- Docker Compose

### Installation & Launch

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/rhamenator/ai-scraping-defense.git](https://github.com/rhamenator/ai-scraping-defense.git)
    cd ai-scraping-defense
    ```
2.  **Configure Environment (Optional):**
    Create a `.env` file in the root directory if you need to set API keys (like `OPENAI_API_KEY`) or customize webhook URLs.
3.  **Build and Run:**
    ```bash
    docker-compose build
    docker-compose up -d
    ```

### Accessing Services

- **Main Website / Docs:** `http://localhost/` (served by NGINX, passes through checks)
- **Tarpit Endpoint (for testing):** `http://localhost/api/tarpit` (triggered by bots/suspicious requests)
- **Admin UI:** `http://localhost/admin/` (proxied by NGINX to the `admin_ui` service)
- **Metrics API:** `http://localhost/admin/metrics` (used by Admin UI frontend)
- **GoAccess Dashboard (if enabled):** `http://localhost:7890`

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
