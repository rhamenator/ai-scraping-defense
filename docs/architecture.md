# System Architecture

This document provides a high-level overview of how the components in the AI Scraping Defense Stack interact.

---

## 🧱 Component Overview & Data Flow

```plaintext
        +-----------------------------+
        |   Web Clients / Bots        |
        +--------------+--------------+
                       | [HTTP/S Request]
                       v
+----------------------+-------------------------------+-------------------------+
| NGINX (Port 80/443)  |                               |                         |
| - Reverse Proxy      |                               |                         |
| - Rate Limiting      |                               |                         |
| - Lua: Blocklist Chk |--->[Check Redis Blocklist DB (2)]-->(Blocked? YES: 403) |
| - Lua: Bot Heuristics|                               |(No)                     |
+---------------------+--------------------------------+-------------------------+
                      | (Passed Checks)                |       (Suspicious? YES) |
                      |                                v                         v
   [Proxy Pass to App]|                   [Redirect /api/tarpit (Internal Location)]
                      |                                |
                      v                                v
   +------------------+----------------+   +-----------+----------------+
   |    Your Real Application          |   | Tarpit API (FastAPI)       |
   | (Served by NGINX or proxied)      |   | - Slow Stream Response     |
   |                                   |   | - Gen. Markov Content      |
   +---------------------------------+     | - Calls Escalation Eng.    |---+ [POST Metadata]
                                           | - Logs Honeypot Hit        |   |
                                           | - Flags IP in Redis DB(1)  |   |
                                           +-------+--------------------+   |
                                                   |                        |
                                                [Log Hit]                   |
                                                   v                        v
+--------------------------------+   +-------------+-----------+   +--------------------+
| AI Service (FastAPI)           |   | Escalation Engine       |   | Log Files          |
| - Receives Webhook (/analyze)  |<--| (FastAPI)               |   | ./logs/            |
| - Adds IP to Redis Blocklist(2)|   | - Heuristics + RF Model |-->| - honeypot_hits    |
| - Sends Alerts (Slack/SMTP...) |   | - Uses Redis Freq. DB(3)|   | - block_events     |
+-------------+------------------+   | - Calls LLM/External API|   | - alert_events     |
              |                      | - Calls Webhook         |   | - escalation       |
              |                      +-----------+-------------+   | - aiservice_errors |
              |                                  ^                 | - nginx/*          |
              | [Webhook Alert]                  |                 +--------------------+
              v                                  | [Read Metrics]
+-----+-------+------------------+               |
| External Systems               |               |
| (Slack, Email, SIEM, Fail2ban) |               v
+--------------------------------+ +-----------+-------------+
                                   | Admin UI (Flask)        |---+ Reads ./metrics.py
                                   | - Serves Dashboard      |
                                   | - Fetches /metrics      |
                                   +-------------------------+

+--------------------------------+   +-------------------------+   +---------------------+
| Redis                          |   | Training Script         |   | Archive Rotator     |
| - DB 1: Tarpit IP Flags        |<--| (rag/training.py)       |   | (Python Scheduler)  |
| - DB 2: Blocklist Set (IPs)    |-->| - Loads Apache Logs     |   | - Runs js_zip_gen   |
| - DB 3: Frequency Tracking     |   | - Loads Feedback Logs   |-->| - Manages ./archives|
+--------------------------------+   | - Loads robots.txt      |   +---------------------+
                                     | - Processes->SQLite DB  |
                                     | - Labels w/ Scores      |
                                     | - Extracts Features     |
                                     | - Trains/Saves RF Model |
                                     | - Exports data for LLM  |
                                     +-------------------------+

# Key Data Flows

These are the primary sequences of interaction between the components of the AI Scraping Defense Stack:

1.  **Incoming Request:** A web client or bot sends an HTTP/S request to the server, which first hits the Nginx reverse proxy.

2.  **Blocklist Check (Nginx):**
    * The Nginx Lua script `check_blocklist.lua` immediately queries Redis Database 2 (the `blocklist:ip` set).
    * If the requesting IP address is found in the blocklist set, Nginx returns a `403 Forbidden` response directly, blocking the request at the edge.
    * If the IP is not found, the request proceeds to the next check.

3.  **Heuristic Check (Nginx):**
    * The Nginx Lua script `detect_bot.lua` analyzes the request headers (User-Agent, Accept, Accept-Language, etc.) and potentially the request URI.
    * Known benign crawlers (e.g., Googlebot) identified by their User-Agent are generally allowed to pass through (unless blocklisted).
    * Requests matching known bad User-Agents or exhibiting suspicious header patterns (e.g., missing crucial headers) are flagged.
    * If flagged as suspicious, Nginx performs an internal redirect to the `/api/tarpit` location.
    * If the request passes heuristic checks and is not blocklisted, it is proxied to the intended backend application (or served directly by Nginx if it's a static file).

4.  **Tarpit Interaction:**
    * The Tarpit API service (`tarpit_api.py`) receives the internally redirected request at its `/tarpit` endpoint.
    * It logs the event as a "Honeypot Hit" to `logs/honeypot_hits.log` using the shared logger (`shared/honeypot_logger.py`).
    * It flags the source IP address temporarily in Redis Database 1 using `ip_flagger.py`.
    * It sends the full request metadata (IP, UA, headers, path, etc.) via a POST request to the Escalation Engine's `/escalate` endpoint.
    * It generates dynamic decoy content (using `markov_generator.py`) or serves a basic loading page.
    * It streams this content back to the client very slowly using `StreamingResponse`.

5.  **Escalation & Analysis:**
    * The Escalation Engine service (`escalation_engine.py`) receives the POST request with metadata at its `/escalate` endpoint.
    * It queries Redis Database 3 to calculate real-time request frequency features for the source IP.
    * It applies heuristic rules based on the metadata and frequency features.
    * It uses the pre-trained Random Forest model (`.joblib` file) loaded from `./models` to predict the probability of the request being a bot, using features extracted from the metadata (including frequency).
    * Based on the combined heuristic score and model prediction, it may optionally make further classification calls to a configured local LLM API or an external commercial classification API.
    * If the final analysis determines the request is likely malicious (based on configured thresholds and API results), it constructs a webhook payload.
    * It sends this payload via a POST request to the AI Service's `/analyze` endpoint.

6.  **AI Service Actions:**
    * The AI Service (`ai_webhook.py`) receives the POST request at its `/analyze` endpoint.
    * It logs the incoming event and the reason for the escalation.
    * It uses the flagged IP address from the payload's details section.
    * It adds this confirmed malicious IP address to the `blocklist:ip` set in Redis Database 2.
    * Based on the configured `ALERT_METHOD` and the severity of the detection reason, it may send out alerts via Slack, SMTP (email), or a generic webhook to notify administrators or trigger external systems (like Fail2ban or SIEMs).

7.  **Training Process (Offline/Periodic):**
    * The `rag/training.py` script is run manually or periodically.
    * It reads historical web server logs (e.g., `apache_access.log`).
    * It reads feedback logs (`honeypot_hits.log`, `captcha_success.log`).
    * It parses logs and loads them into a temporary SQLite database (`log_analysis.db`).
    * It iterates through the database, extracts features for each request (querying the DB itself for historical frequency/timing data).
    * It labels each request as 'bot', 'human', or 'suspicious' based on heuristics and feedback data.
    * It trains a Random Forest classifier using the high-confidence ('bot'/'human') labeled data and extracted features.
    * It saves the trained model pipeline (including the feature vectorizer) to `./models/bot_detection_rf_model.joblib`.
    * It optionally exports high-confidence labeled data in JSONL format for fine-tuning language models.

8.  **Honeypot Rotation:**
    * The `rotating_archive.py` script runs periodically (e.g., via `schedule` library).
    * It calls `js_zip_generator.py` to create a new fake JavaScript ZIP archive in the `./archives` directory.
    * It lists existing archives in that directory and deletes the oldest ones, keeping only a configured number (e.g., the latest 5).

9.  **Metrics Monitoring:**
    * Various services (`escalation_engine.py`, `tarpit_api.py`, `ai_webhook.py`, etc.) import the shared `metrics.py` module.
    * As events occur (e.g., tarpit hit, escalation received, bot detected, webhook sent), services call `increment_metric()` to update counters in the shared `metrics_store`.
    * The Admin UI service (`admin_ui.py`) serves a web dashboard.
    * The dashboard's frontend JavaScript periodically fetches data from the Admin UI's `/metrics` endpoint, which in turn calls `get_metrics()` from `metrics.py` to retrieve the latest counter values and uptime.
