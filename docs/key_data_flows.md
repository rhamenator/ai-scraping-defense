
# Key Data Flows

This document outlines the primary sequences of interaction between the components of the AI Scraping Defense Stack.

1. **Incoming Request:** Hits Nginx.

2. **Blocklist Check:** Nginx Lua checks Redis DB 2 (`blocklist:ip` set). If IP is present, request is blocked (403).

3. **Heuristic Check:** Nginx Lua (`detect_bot.lua`) applies UA and header checks. Benign bots are allowed (unless blocked). Suspicious requests are internally redirected to `/api/tarpit`. Legitimate requests are proxied to the real application (or served directly by Nginx).

4. **Tarpit:** The Tarpit API (`tarpit_api.py`) receives the redirected request.
    * Logs the hit to `honeypot_hits.log`.
    * Flags the IP in Redis DB 1 (temporary flag).
    * Sends request metadata to the Escalation Engine (`/escalate`).
    * Serves a slow, dynamically generated response.

5. **Escalation:** The Escalation Engine (`escalation_engine.py`) receives metadata.
    * Calculates real-time frequency using Redis DB 3.
    * Runs heuristic rules.
    * Uses the trained RF model (`.joblib`) for prediction.
    * Optionally calls local LLM or external classification APIs.
    * Based on the final score/classification, calls the AI Service webhook (`/analyze`) if deemed malicious.

6. **AI Service:** The AI Service (`ai_webhook.py`) receives the webhook.
    * Logs the event.
    * Adds the confirmed malicious IP to the Redis DB 2 blocklist set.
    * Sends alerts based on configuration (`ALERT_METHOD`).

7. **Training (Offline/Periodic):**
    * The `training.py` script reads logs (`apache_access.log`, `honeypot_hits.log`, `captcha_success.log`), loads them into SQLite, extracts features (including frequency calculated via DB queries), labels data, trains the RF model (saving to `./models`), and exports data for potential LLM fine-tuning.

8. **Archive Rotation:** The `rotating_archive.py` script periodically generates new JS ZIP honeypots in `./archives` and cleans up old ones.

9. **Monitoring:** The Admin UI (`admin_ui.py`) reads metrics from the shared `metrics.py` module (updated by various services) and displays them.
