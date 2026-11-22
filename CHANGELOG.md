# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

* `scripts/find_logged_webhook_urls.py` finds webhook URLs that earlier releases may have written to logs (#1906), so you can decide whether any rotation is needed. It scans the files or directories you give it for Slack, Teams and Discord webhook URLs and for the webhook URLs configured in the environment or a `.env` file, and reports file, line, kind and a short fingerprint. It never prints a URL and changes nothing.
* Admin Security page (`/security`, admin only): shows the signed-in identity and sign-in method, whether a passkey is enrolled, whether TOTP is set up, and how many backup codes remain, with a confirmed Regenerate action and Sign out (#1952). New codes are shown once, uncached, and removed from the page when dismissed or when the page is left. `POST /mfa/backup-codes` now requires the CSRF token (`X-CSRF-Token` matching the `csrf_token` cookie) because regenerating invalidates every earlier code; API clients that call it with Basic credentials alone must send it.
* Admin Logs page: search block events by address or reason, filter by time range (last hour, 24 hours, 7 days, 30 days, all), page beyond the newest 50 and export the current filter as CSV with spreadsheet-formula neutralisation (#1951). Query parameters are validated server-side (page size at most 200, search at most 100 characters); only the newest 100,000 log lines are searched and the export holds at most 10,000 rows, both stated on the page.
### Fixed

* Fix the Settings page GDPR deletion form (#1958): its script read the `HttpOnly` CSRF cookie, so the token was always empty and every request was refused. The token is now rendered into the page and read from there.
* Admin dashboard: browse, search, block and unblock addresses from the Blocklist section (#1950). Every change names the exact address in a confirmation step and shows API errors to the admin. `POST /block` and `POST /unblock` now require the CSRF token (`X-CSRF-Token` matching the `csrf_token` cookie, which the dashboard page sets); API clients that call them with Basic credentials alone must send it. `POST /block` accepts an optional `reason` (at most 200 characters) that is written to the audit log.

### Security

* Webhook URLs no longer reach the logs (#1906). The alert and escalation services logged the configured webhook URL, and the HTTP library's error text repeats the full request URL, so a Slack, Teams or Discord token in the path could end up in log files. Logs now carry only the origin plus a short fingerprint, and a shared filter and `log_error` scrub URLs that have a path, query, fragment or user info from messages and exception text. **Rotate any webhook URL that earlier releases may have logged.** `SECURITY.md` now lists webhook URLs as secrets.
* Bind published ports to loopback by default (#1914): in `docker-compose.yaml` only `nginx_proxy` (80/443) publishes on every interface; the admin and cloud dashboards, Prometheus, Grafana, Traefik (and its API), the model servers, Postgres, Redis, Mailhog and the other development endpoints now bind to `${PUBLISH_ADDRESS:-127.0.0.1}`. Set `PUBLISH_ADDRESS` to a private interface address to reach them from another machine. Not yet done under #1914: a generated Grafana admin credential.
* `deploy-prod.yml` no longer interpolates the `version_tag` dispatch input into the shell script (#1910): it is passed through the environment and validated as a container tag before use.
* Harden container updates and Docker API access (#1913): every image in `docker-compose.yaml` and the `Dockerfile` base images, and the OpenResty image in `kubernetes/nginx-deployment.yaml`, is pinned by digest; Watchtower is now opt-in (`docker compose --profile auto-update up -d`) and only updates containers labelled `com.centurylinklabs.watchtower.enable=true`, daily by default (`WATCHTOWER_INTERVAL`, was every 60 seconds for everything); Traefik no longer mounts the raw Docker socket and instead discovers containers through a read-only `docker_socket_proxy` on an internal network that refuses everything except reading containers. The base-image digests are build arguments (`PYTHON_DIGEST`, `RUST_DIGEST`): a `PYTHON_VERSION` or `RUST_VERSION` fallback must be given together with the digest of that image, and the build fails with a clear message if they disagree. The socket proxy runs with all capabilities dropped, a read-only filesystem and no-new-privileges, and is listed in the security-hardening baseline. **Upgrade note:** if you relied on Watchtower starting automatically, add the profile and the label; bump the pinned digests deliberately when you update images.
* Regenerate `requirements.lock` for the merged dependency bumps: fastapi 0.165.0, mistralai 3.8.0 and xgboost 3.4.1 (matching the new `requirements.txt` ranges), python-multipart 0.0.34. `pip-audit` reports no known vulnerabilities for the lock.
* Harden the canary-shift workflow (#1909): it runs in the `production` environment (reviewer approval), takes only a validated whole-number `weight`, no longer accepts a namespace or ingress name (both fixed), and passes values to shell through environment variables instead of interpolating workflow inputs into shell source. A test guards each of these. Operators should move the GCP secrets to the `production` environment and restrict the service account to the canary ingress (see `docs/promotion-and-canary.md`).
* Update the locked dependencies that `pip-audit` flagged on `main`: opentelemetry packages 1.45.1 to 1.45.2 (CVE-2026-126360, trace-context extraction) and soupsieve 2.9.2 to 4.1.3 (CVE-2026-126190 to -126193, selector ReDoS and deep recursion, used through beautifulsoup4 in the e2e tools). `pip-audit` now reports no known vulnerabilities for `requirements.lock`.

### Removed

* The autofix workflows (`autofix-and-guard.yml`, `autofix.yml`, `security-autofix.yml`, the `autofix` job and input in the comprehensive audits and `master-problem-detection.yml`, and the unused `.github/tools/autofix.sh`) (#1911). They had run once, failed, and combined unpinned tool downloads, a write token and default automerge. The audits themselves remain and now run with read-only repository permissions.

### Security

* Disable HTTP/2 and TLS 1.3 in the bundled OpenResty TLS examples and generated listener while its NGINX core remains below the 1.30.7/1.31.9 fixes. Add a CI guard against enabling the affected optional modules or TLS 1.3 (#1944). TLS clients must support TLS 1.2 until a patched OpenResty image is available.

## [0.0.16] - 2026-11-20

### Fixed

* Refuse a blocklisted address on `location /` as well. `location /` sets its own `access_by_lua_file`, which replaced the server-level `check_blocklist.lua`, so addresses blocked in Redis were still served on the main content location. The check now lives in `nginx/lua/blocklist.lua` and `detect_bot.lua` runs it first (#1941).

## [0.0.15] - 2026-11-20

### Changed

* Relocate working notes, issue-triage data, license summary and historical
  presentation into docs; update maintenance consumers and remove unused snapshots.

### Fixed

* Apply robots policy consistently in Python escalation scoring and HTTP
  enforcement. Remove UA-only crawler discounts; retain +0.6 robots evidence and
  route a violation directly to the configured block tier before classifiers.

* Parse NGINX robots rules with RFC 9309 case/encoding/comment semantics,
  full-root disallows, allow precedence, wildcard/anchor and agent-group support.

* Require cached forward-confirmed reverse DNS for Googlebot/Bingbot exemptions
  at the NGINX edge; unverified claims receive normal checks and offensive-tool
  UAs cannot bypass detection by including a benign crawler token.

* Enforce the NGINX robots.txt disallow check for every client before User-Agent
  exemptions and heuristic scoring, routing violations directly to the tarpit.

* Strip client-supplied SAML identity headers (`X-SSO-User`, `X-SSO-Groups`) at
  the public Kubernetes NGINX `/admin/` route; SAML needs a separate trusted
  identity-aware gateway.

## [0.0.14] - 2026-11-13

### Fixed

* Send supported request metadata to Request Guard MCP classification and use
  its validated verdict and score in escalation scoring; retain heuristic
  fallback for classifier errors.
* Repair the scheduled alert manager import.

### Changed

* Update routine dependencies and GitHub Actions pins after CI verification.

## [0.0.13] - 2026-11-03

### Fixed

* Return MCP 2.3 structured tool results directly from the adapter and convert
  WebSocket authentication handshake failures to safe error responses.

## [0.0.12] - 2026-11-02

### Added

* Added cooldown-limited attack incident alerts with recent-window thresholds,
  Cloudflare operator guidance, and health-gated manual failover guidance.

### Fixed

* Corrected proxy and tarpit forwarding behavior found in the Python end-to-end
  regression run.
* Repaired the scheduled security-issue and closed-issue maintenance workflows.
* Adapted passkey credential verification for WebAuthn 3.

### Security

* Updated pyasn1 and Rust ZIP pins to resolve reported vulnerabilities.

### Changed

* Updated Python dependency minimums, the reproducible lockfile, and pinned
  GitHub Actions after audit and CI validation.

## [0.0.11] - 2026-10-22

### Changed

* Updated runtime dependencies, including Redis, pandas, and Google Gen AI,
  and refreshed pinned GitHub Actions after review and CI verification.
* Updated OpenTelemetry to 1.45.1 and Black to 26.10.1 to address
  CVE-2026-114603 and CVE-2026-114134.

## [0.0.10] - 2026-10-21

### Fixed

* Removed unused build tools and their vendored dependencies from the cloud
  proxy and prompt router images, and required patched `msgpack` in the cloud
  proxy image.

## [0.0.9] - 2026-10-21

### Fixed

* Removed unused package-build and virtual environment tools from the runtime
  container, eliminating their bundled vulnerable dependencies.

## [0.0.8] - 2026-10-21

### Fixed

* Enforced `X-API-Key` on `GET /list` when the public blocklist's key
  requirement is enabled (GHSA-gh5c-m6x2-g9xj).
* Isolated rate-limit and audit activity from trusted proxies that omit a valid
  forwarded client identity, without promoting infrastructure addresses to
  actionable client IPs.
* Authenticated AI webhook bodies before parsing and normalized equivalent IP
  addresses in blocklist operations.
* Required a trusted SHA-256 digest before loading local model artifacts.
* Updated vulnerable Python dependencies, including `aiohttp`, `certifi`,
  `pip`, `setuptools`, `urllib3`, and `virtualenv`.

### Changed

* Removed the extra package index from the default dependency constraints.
* Local model deployments must configure the model artifact's trusted digest.

## [0.0.7] - 2026-08-12

### Added
* **Selectable Audit Storage:** Security events can now use SQLite or PostgreSQL through `AUDIT_STORAGE_BACKEND`, with bounded loading/export and startup validation.
* **OTLP Trace Export:** Shared FastAPI observability can export W3C-correlated traces over OTLP/gRPC when `OTEL_EXPORTER_OTLP_ENDPOINT` is configured.
* **Cloudflare-Aware Client Identity:** Trusted CDN proxy ranges restore the originating client address while preventing Cloudflare edge addresses from becoming block targets.
* **Operational Hardening:** Added durable security-event export, internal-service authentication controls, attack-regression profiles, data-protection defaults, and deployment validation safeguards.
* **Trusted TLS Fingerprints:** Added JA3/JA4 capture at validated proxy/CDN boundaries and preserved that provenance through escalation and MCP model calls.
* **Threat Model Document:** Added docs/threat_model.md and linked from the README.
* **Automated Dependency Scanning:** Added Dependabot configuration and pip-audit workflow.


### Changed

* **Optional Kubernetes Dependencies:** Kubernetes 35.x removes the former `urllib3<2.4.0` constraint, allowing patched urllib3 releases.
* **Runtime Dependencies:** Refreshed Python and Rust extension dependencies, including the rand soundness-advisory update.
* **Release and Deployment Tooling:** Hardened installers, CI workflows, staging validation, container publishing, and release metadata.
* **Markov Training Utility:** Removed `rag/train_markov_postgres.py` and now build the Markov model using the Rust `markov-train-rs` crate via `train_from_corpus_rs`.
* **Environment Variables:** Replaced deprecated `TARPIT_MAX_HOPS` and `TARPIT_HOP_WINDOW_SECONDS` with `TAR_PIT_MAX_HOPS` and `TAR_PIT_HOP_WINDOW_SECONDS`.
* **Private Upstream Protection:** Pay-per-crawl now blocks private and special-purpose upstream resolutions by default; private service deployments must explicitly set `UPSTREAM_BLOCK_PRIVATE_IPS=false` and provide an equivalent egress boundary.
* **Documentation:** Updated repository references to highlight `src/`, `scripts/`, and `rag/` directories.

### Fixed

* Prevented trusted CDN proxy addresses and credentials embedded in service endpoints from leaking into audit or operational logs.
* Corrected proxy identity, payment, workflow, configuration-validation, and production failure-handling defects found during release hardening.
* Prevented concurrent pay-per-crawl charges from overspending a crawler balance.
* Configured the full Compose profile to store security events in its PostgreSQL
  service so read-only, non-root containers do not depend on writable SQLite paths.
* Replaced fast, unkeyed crawler-token audit hashes with keyed HMAC identifiers;
  deployments can set `CRAWLER_AUDIT_HMAC_KEY` for stable cross-restart correlation.
* Corrected Compose TLS certificate paths so the read-only Nginx container can
  start successfully when HTTPS is enabled.

## **[0.0.5] - 2025-05-25**

### **Added**

* **Kubernetes PostgreSQL Schema Initialization:** Implemented automatic schema initialization for PostgreSQL in Kubernetes by mounting db/init_markov.sql via a new postgres-init-script-cm ConfigMap into the standard /docker-entrypoint-initdb.d/ directory of the PostgreSQL container. This removes the need for manual schema setup in Kubernetes.
* **Helper Script for Local Setup:** Added scripts/linux/setup_local_dirs.sh to assist users in creating the necessary local directory structure and placeholder secret files.

### **Changed**

* **Nginx robots.txt Handling (Docker Compose):** Updated nginx/lua/detect_bot.lua (for Docker Compose deployments) to dynamically load and parse robots.txt rules from the mounted /etc/nginx/robots.txt file, ensuring consistent behavior with Kubernetes for benign bot rule checking.
* **Kubernetes SYSTEM_SEED Management:**
  * Moved SYSTEM_SEED from kubernetes/configmap.yaml to kubernetes/secrets.yaml (under a new system-seed-secret) for enhanced security.
  * Updated kubernetes/tarpit-api-deployment.yaml to source the SYSTEM_SEED environment variable from this new Secret.
* **Kubernetes Image Placeholders:** Standardized placeholder image names (e.g., your-registry/ai-defense-python-base:latest, your-registry/ai-defense-nginx:latest) across all relevant Kubernetes YAML files (*-deployment.yaml,*-cronjob.yaml) to clarify where user-specific image URIs should be inserted.
* **Documentation (mkdocs.yml):** Corrected the "License Summary" link in nav section to point to license_summary.md.
* **Documentation (docs/model_adapter_guide.md):** Updated to include the /metrics endpoint for the Escalation Engine.
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
