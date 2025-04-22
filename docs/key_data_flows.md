# Key Data Flows

This document outlines the primary sequences of interaction between the components of the AI Scraping Defense Stack, incorporating the latest changes.

1. **Incoming Request:** Hits Nginx.

2. **Blocklist Check:** Nginx Lua (`check_blocklist.lua`) checks Redis DB 2 (`blocklist:ip` set). If the IP is present, the request is immediately blocked (403 response).

3. **Heuristic & `robots.txt` Check:** Nginx Lua (`detect_bot.lua`) applies User-Agent and header checks.
    * If the User-Agent matches a known benign bot, its requested path is checked against `robots.txt` rules. If violating rules, it's redirected to the Tarpit API. If compliant, it's proxied to the real application.
    * If not a known benign bot, heuristic checks are applied. Suspicious requests are redirected to the Tarpit API.
    * Requests passing all checks are proxied to the real application backend (defined by `REAL_BACKEND_HOST`).

4. **Tarpit:** The Tarpit API (`tarpit_api.py`) receives the redirected request.
    * Logs the hit to `honeypot_hits.log` (if enabled).
    * Flags the IP in Redis DB 1 (temporary visit flag).
    * **Hop Limit Check:** Increments and checks the IP's request count in Redis DB 4 against `TAR_PIT_MAX_HOPS`. If the limit is exceeded:
        * Adds the IP to the blocklist in Redis DB 2 with TTL `BLOCKLIST_TTL_SECONDS`.
        * Returns an immediate 403 Forbidden response.
        * (Processing stops here for this request)
    * **Escalation:** If the hop limit is *not* exceeded, sends request metadata to the Escalation Engine (`/escalate`).
    * **Content Generation:**
        * Seeds the random generator using `SYSTEM_SEED` and a hash of the requested path.
        * Queries the **PostgreSQL database** using the seeded state to generate Markov chain text.
        * Generates fake internal links using the seeded state.
    * **Response:** Serves the slow, deterministically generated HTML response.

5. **Escalation:** The Escalation Engine (`escalation_engine.py`) receives metadata from the Tarpit API.
    * Calculates real-time frequency using Redis DB 3.
    * Runs heuristic rules.
    * Uses the trained Random Forest model (`.joblib`) for prediction.
    * Optionally calls local LLM, external classification APIs, or IP reputation services.
    * Based on the final score/classification, calls the AI Service webhook (`/analyze`) if deemed malicious.

6. **AI Service:** The AI Service (`ai_webhook.py`) receives the webhook for confirmed malicious requests.
    * Logs the event.
    * Adds the confirmed malicious IP to the Redis DB 2 blocklist set with TTL `BLOCKLIST_TTL_SECONDS`.
    * Optionally reports the IP to community blocklists.
    * Sends alerts based on configuration (`ALERT_METHOD`).

7. **Training (Offline/Periodic):**
    * **ML Model:** The `training.py` script reads logs (`apache_access.log`, `honeypot_hits.log`, `captcha_success.log`), loads them into SQLite, extracts features, labels data, trains the RF model (saving to `./models`), and exports data for potential LLM fine-tuning.
    * **Markov Model:** The `train_markov_postgres.py` script reads a text corpus file, tokenizes it, and populates the `markov_words` and `markov_sequences` tables in the **PostgreSQL** database.

8. **Archive Rotation:** The `rotating_archive.py` script periodically generates new JS ZIP honeypots in `./archives` and cleans up old ones.

9. **Monitoring:** The Admin UI (`admin_ui.py`) reads metrics from the shared `metrics.py` module (updated by various services) and displays them. Optionally dumps metrics to JSON if configured.
