# Key Data Flows

This document outlines the primary sequences of interaction between the components of the AI Scraping Defense Stack, incorporating the latest automation for `robots.txt` and corpus management.

## Automated Background Data Preparation (Kubernetes CronJobs)

1. **`robots.txt` Fetching (Periodic):**
    * A Kubernetes CronJob (`robots-txt-fetcher`) executes `util/robots_fetcher.py` on a defined schedule (e.g., daily).
    * The script fetches `/robots.txt` from the `REAL_BACKEND_HOST` (your actual application).
    * **If successful:** The fetched `robots.txt` content is written to a Kubernetes ConfigMap (`live-robots-txt-config`).
    * **If fetching fails (e.g., 404):** A default, restrictive `robots.txt` is written to the `live-robots-txt-config` ConfigMap, and an error is logged.
    * This ConfigMap is mounted as a file (e.g., `/etc/nginx/live_robots.txt`, `/app/config/live_robots.txt`) into relevant pods (Nginx, Escalation Engine).

2. **Wikipedia Corpus Generation (Periodic):**
    * A Kubernetes CronJob (`corpus-wikipedia-updater`) executes `util/corpus_wikipedia_updater.py` on a defined schedule (e.g., daily).
    * The script fetches content from several random Wikipedia articles.
    * The cleaned text content is appended to a file (e.g., `wikipedia_corpus.txt`) stored on a PersistentVolumeClaim (`corpus-data-pvc`).

3. **Markov Model Training (Periodic):**
    * A Kubernetes CronJob (`markov-model-trainer`) executes `rag/train_markov_postgres.py` on a defined schedule (e.g., daily, typically after the corpus update).
    * The script reads the `wikipedia_corpus.txt` from the `corpus-data-pvc`.
    * It tokenizes the text and populates/updates the `markov_words` and `markov_sequences` tables in the PostgreSQL database.

## Real-time Request Processing Flow

1. **Incoming Request:** An HTTP/S request from a web client or bot hits the Nginx reverse proxy.

2. **Nginx Edge Filtering (Lua Scripts):**
    * **Blocklist Check (`check_blocklist.lua`):**
        * The connecting IP address is checked against individual IP keys (e.g., `blocklist:ip:1.2.3.4`) in Redis (DB 2).
        * If the IP key exists (indicating it's blocklisted), Nginx immediately returns a 403 Forbidden response. Request processing stops.
    * **Bot Detection & `robots.txt` Compliance (`detect_bot.lua`):**
        * If the IP is not blocklisted, this script analyzes the User-Agent and other headers.
        * It reads and parses rules from the mounted `live_robots.txt` (sourced from the `live-robots-txt-config` ConfigMap).
        * **Known Benign Bots:** If the User-Agent matches a known benign crawler (e.g., Googlebot):
            * Its requested path is checked against the rules from `live_robots.txt`.
            * If violating rules, the request is internally redirected to the Tarpit API (`/api/tarpit`).
            * If compliant, Nginx proxies the request to the `REAL_BACKEND_HOST`.
        * **Other Clients/Unknown Bots:** Heuristic checks are applied.
            * If deemed highly suspicious based on User-Agent or header patterns, the request is internally redirected to the Tarpit API.
            * Requests passing these initial checks are proxied to the `REAL_BACKEND_HOST`.

3. **Tarpit Engagement (`tarpit_api.py`):**
    * Receives requests redirected by Nginx.
    * Logs the hit (e.g., to `honeypot_hits.log`).
    * Flags the IP in Redis (DB 1 - temporary visit flag).
    * **Hop Limit Check:** Increments and checks the IP's request count in Redis (DB 4) against `TAR_PIT_MAX_HOPS`.
        * If the limit is exceeded, the IP is added to the main blocklist in Redis (DB 2) with a TTL, and an immediate 403 Forbidden response is returned. Request processing stops.
    * **Escalation:** If the hop limit is *not* exceeded, the Tarpit API sends request metadata (IP, User-Agent, headers, path) to the Escalation Engine's `/escalate` endpoint.
    * **Content Generation:**
        * Seeds a random number generator using a combination of `SYSTEM_SEED` and a hash of the requested path for deterministic output.
        * Queries the PostgreSQL database (populated by `train_markov_postgres.py`) to generate Markov chain text.
        * Generates plausible but fake internal links.
    * **Response:** Streams the slow, deterministically generated HTML response back to the client.

4. **Suspicion Escalation & Analysis (`escalation_engine.py`):**
    * Receives metadata from the Tarpit API via the `/escalate` endpoint.
    * Performs real-time frequency analysis of requests from the IP using Redis (DB 3).
    * Applies heuristic rules based on request characteristics.
    * Utilizes the pre-trained Random Forest model (loaded from `models-pvc`) for a bot probability score.
    * Considers information from the dynamically fetched `live_robots.txt` if relevant to its internal logic (e.g., if certain paths are inherently more suspicious).
    * Optionally, calls external services:
        * IP reputation check services.
        * Local or external LLM/classification APIs for deeper analysis.
    * Based on a combined final score or definitive classification:
        * If deemed malicious, it sends a webhook with details (IP, reason, original request metadata) to the AI Service's `/analyze` endpoint.
        * Optionally, it might trigger a CAPTCHA challenge (this part is a hook; actual CAPTCHA serving/verification is external).

5. **AI Service Actions (`ai_webhook.py`):**
    * Receives webhook data from the Escalation Engine for confirmed malicious requests via the `/analyze` endpoint.
    * Logs the block event.
    * Adds the confirmed malicious IP address as an individual key (e.g., `blocklist:ip:1.2.3.4`) to the Redis blocklist (DB 2) with a configured TTL (`BLOCKLIST_TTL_SECONDS`). This IP will be caught by Nginx's `check_blocklist.lua` on subsequent requests.
    * Optionally, reports the IP to configured community blocklist services (e.g., AbuseIPDB).
    * Dispatches alerts based on the `ALERT_METHOD` configuration (e.g., SMTP, Slack, generic webhook).

## Other Supporting Flows

* **Admin UI (`admin_ui.py`):** Periodically fetches metrics from the shared `metrics.py` module (which is updated by various services like Tarpit, Escalation, AI Service) and displays them on a web dashboard.
* **Archive Rotator (`rotating_archive.py`):** Runs as a Deployment (or could be a CronJob). Periodically generates new fake JavaScript ZIP archives and saves them to `archives-pvc`. Old archives are cleaned up. Nginx serves these archives from the same `archives-pvc`.
* **ML Model Training (`training.py` - Manual/Future Job):** This script is run manually or could be set up as a Kubernetes Job. It reads logs (e.g., Apache access logs, honeypot logs), extracts features, labels data, and (re)trains the Random Forest model, saving it to `models-pvc`.

This detailed flow should give a clear picture of how the system now operates with the automated components.
