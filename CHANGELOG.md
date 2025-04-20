# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
