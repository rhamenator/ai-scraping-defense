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
       +--------------+--------------+
       |        NGINX (Port 80)      |---+  Reads config from ./nginx/nginx.conf
       | (Reverse Proxy, Lua Filter) |
       +--------------+--------------+
                      |
+-----------------------+--------------------------+----------------------------+
| [Request Passes?]     |                          |                            |
| Lua: check_blocklist->| Check Redis Blocklist DB |                            |
+-----------------------+--------------------------+                            |
                      | (No: Block 403)                                        |
                      v                                                        |
       +--------------+--------------+                                        |
       | Lua: detect_bot.lua         |                                        |
       | - Basic UA/Header Checks    |                                        |
       +--------------+--------------+                                        |
                      |                                                        |
    (Suspicious?)--> YES --> [Redirect /api/tarpit] -->+                        |
                      |                                |                        |
                     NO                                |                        |
                      | [Proxy Pass]                   |                        |
                      v                                v                        |
   +------------------+----------------+   +-----------+-------------+         |
   |    Your Real Application         |   | Tarpit API (FastAPI)    |         |
   | (Served by NGINX or proxied)    |   | - Slow Stream Response  |<---+    | [Read Archives]
   |                                 |   | - Gen. Markov Content   |    |    |
   +---------------------------------+   | - Calls Escalation Eng. |    |    v
                                       | - Logs Honeypot Hit     |    | +----------+---------+
                                       +-----------+-------------+    | | Archive Rotator   |
                                                   |                  | | (Python Scheduler)|
                         [POST Metadata] -->+      | [Log Hit]        | | - Runs js_zip_gen |
                                          |      |                  | | - Manages ./archives|
                                          v      v                  | +---------------------+
+--------------------------------+   +----+------+-------------+    | +----------+---------+
| AI Service (FastAPI)           |   | Escalation Engine       |    | |   Log Files        |
| - Receives Webhook (/analyze)  |   | (FastAPI)               |<---+ | ./logs/            |
| - Adds IP to Redis Blocklist <-----| - Heuristics + RF Model |      | - honeypot_hits    |
| - Sends Alerts (Slack/SMTP)    | +-| - Uses Redis Frequency  |      | - block_events     |
+--------------------------------+ | | - Calls LLM/External API|      | - alert_events     |
                                   | | - Calls Webhook         |      | - escalation       |
      +----------------------------+ +-----------+-------------+      | - aiservice_errors |
      | [Webhook Alert]                          ^                      +--------------------+
      v                                          |
+-----+--------------------------+               | [Read Metrics]
| External Systems               |               |
| (Slack, Email, SIEM, PagerDuty)|               v
+--------------------------------+   +-----------+-------------+
                                   | Admin UI (Flask)        |---+ Reads ./metrics.py
                                   | - Serves Dashboard      |
                                   | - Fetches /metrics      |
                                   +-------------------------+

+--------------------------------+   +-------------------------+
| Redis                          |   | Training Script         |
| - DB 0: (Default/Unused)       |   | (rag/training.py)       |
| - DB 1: Tarpit IP Flags        |   | - Loads Apache Logs     |
| - DB 2: Blocklist Set          |<--| - Loads Feedback Logs   |---< Reads ./logs/*
| - DB 3: Frequency Tracking     |-->| - Loads robots.txt      |---< Reads ./config/*
+--------------------------------+   | - Processes->SQLite DB  |---> Writes ./data/*.db
                                   | - Labels w/ Scores      |
                                   | - Extracts Features     |
                                   | - Trains/Saves RF Model |---> Writes ./models/*.joblib
                                   | - Exports data for LLM  |---> Writes ./data/finetuning*
                                   +-------------------------+