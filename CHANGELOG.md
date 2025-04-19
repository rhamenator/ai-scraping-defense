# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial structure for NGINX reverse proxy with Lua support.
- FastAPI service skeleton for tarpit (`/tarpit`).
- FastAPI service skeleton for escalation engine (`/escalate`).
- Flask service skeleton for Admin UI (`/admin`, `/metrics`).
- Basic `metrics.py` module for in-memory stats tracking.
- Python script placeholders for Markov generator, JS ZIP generator, email entropy scanner, webhook forwarder.
- Docker Compose setup for multi-container orchestration.
- Base `Dockerfile` with core dependencies.
- `README.md`, `LICENSE` (GPL-3.0), `LICENSE.md`, `CONTRIBUTING.md`, `SECURITY.md`.
- `.gitignore` file.
- GitHub Actions CI workflow (`ci.yml`) and PR labeler (`labeler.yml`).
- Issue and Pull Request templates (`.github/`).
- Documentation structure (`/docs`) with placeholders for architecture, API reference, legal info.
- Synthetic corpus generator (`synthetic_data_generator.py`).
- Wikipedia random page scraper (`wiki_scraper_generator.py`).
- Slow streaming HTML response logic in tarpit API.
- Rotating archive logic for JS honeypots.
- Webhook integration in escalation engine.
- Fake page generation with Markov text and randomized links.
- Admin UI template (`admin_ui/templates/index.html`).
- GoAccess configuration (`goaccess/goaccess.conf`).

### Changed

- Refined escalation pipeline logic (heuristic -> local LLM -> external API -> webhook).
- Improved honeypot field obfuscation using dynamic generation and realistic naming.
- Made tarpit response streaming more robust using FastAPI's `StreamingResponse`.
- Switched Markov generator corpus source from Wikipedia scraping to synthetic data, then back to optional Wikipedia scraping based on user preference.
- Refined directory structure for clarity (e.g., separating services).
- Updated `docker-compose.yml` to include all services and networks.

### Fixed

- Corrected placeholder count mismatch in JS template generator.
- Fixed file path issues for Windows compatibility during testing.
- Removed emojis from README for better PDF compatibility.

## [0.1.0] - YYYY-MM-DD

*(This would be your first tagged release)*

### Added

- Initial stable release of the AI Scraping Defense Stack.
- Core functionality: NGINX/Lua detection, Tarpit API, Basic Escalation, Admin Metrics UI.
- Documentation V1.
