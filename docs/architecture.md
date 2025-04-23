# System Architecture

This document provides a high-level overview of how the components in the AI Scraping Defense Stack interact.

---

## 🧱 Component Overview & Data Flow

The system employs a layered approach:

1. **Edge Filtering (Nginx + Lua):** Incoming requests first hit Nginx. Lua scripts perform initial checks:
    * IP is checked against the Redis blocklist (DB 2). Blocked IPs get a 403 response immediately.
    * Basic request heuristics (User-Agent, headers) and `robots.txt` compliance (for known benign bots) are evaluated.
    * Requests deemed safe and compliant are proxied to the real backend application (defined by `REAL_BACKEND_HOST`).
    * Suspicious requests or benign bots violating `robots.txt` are internally redirected to the Tarpit API.

2. **Tarpit & Escalation:**
    * **Tarpit API (FastAPI):** Receives redirected requests.
        * Logs the hit and flags the IP visit (Redis DB 1).
        * Checks a hop counter for the IP (Redis DB 4). If the configured limit (`TAR_PIT_MAX_HOPS`) is exceeded within the time window (`TAR_PIT_HOP_WINDOW_SECONDS`), it triggers an immediate block by adding the IP to Redis DB 2 and returns a 403.
        * If the limit is not exceeded, it sends request metadata to the Escalation Engine.
        * Generates deterministic fake page content (using Markov chains from PostgreSQL) and links (seeded by URL hash and `SYSTEM_SEED`).
        * Streams the fake page slowly back to the client.
    * **Escalation Engine (FastAPI):** Analyzes metadata from the Tarpit API.
        * Performs frequency analysis using Redis DB 3.
        * Applies heuristic scoring and runs a pre-trained Random Forest model.
        * Optionally calls external IP reputation services or local/external classification APIs (e.g., LLMs).
        * If the request is deemed malicious based on scoring and checks, it forwards details to the AI Service.

3. **AI Service & Actions:**
    * **AI Service (FastAPI):** Receives confirmed malicious request data.
        * Adds the offending IP address to the Redis blocklist (DB 2) with a configurable TTL.
        * Optionally reports the IP to configured community blocklists.
        * Dispatches alerts via configured methods (Slack, SMTP, Webhook).

4. **Monitoring & Background Tasks:**
    * **Admin UI (Flask):** Fetches real-time metrics from a shared Python `Counter` object. Optionally dumps metrics to JSON.
    * **Archive Rotator:** Background service periodically generates new JS ZIP honeypots.
    * **Training Scripts:** Offline scripts use logs and other data to train the ML model (`rag/training.py`) and populate the PostgreSQL Markov database (`rag/train_markov_postgres.py`).

---

### Mermaid Diagram

```mermaid
flowchart TD
    subgraph "User Interaction & Edge"
        A["Web Clients or Bots"] -- HTTP/S Request --> B(NGINX Port 80/443);
        B -- Checks --> C{"Blocklist Check (Lua + Redis DB 2)"};
        C -- Blocked --> D[Return 403];
        C -- Not Blocked --> E{"Heuristic & robots.txt Check (Lua)"};
        E -- Passed --> G["Proxy Pass"];
        E -- Suspicious/Violating --> F["Internal Redirect /api/tarpit"];
    end

    subgraph "Real Application"
        G -- Proxied To --> I["Your Web Application (REAL_BACKEND_HOST)"];
    end

    subgraph "Tarpit & Escalation Pipeline"
        F --> H(Tarpit API - FastAPI);
        H -- Logs Hit --> R["logs/honeypot_hits.log"];
        H -- Flags IP --> RedisDB1[(Redis DB 1 Tarpit Flags)];
        H -- Reads/Updates Hop Count --> RedisDB4[(Redis DB 4 Hop Counts)];
        H -- Updates --> MetricsStore[(Metrics Store)];
        H -- Hop Limit Exceeded --> BLOCK[Add IP to Redis DB 2];
        BLOCK --> D;
        H -- Hop Limit OK --> POSTMETA[POST Metadata];
        POSTMETA --> L(Escalation Engine - FastAPI);
        H -- Reads Markov Chain --> PGDB[(PostgreSQL Markov DB)];

        L -- Uses/Updates --> RedisDB3[(Redis DB 3 Freq Tracking)];
        L -- Updates --> MetricsStore;
        L -- If Malicious --> M(AI Service - FastAPI);
    end

    subgraph "AI Service & Actions"
        M -- Adds IP --> RedisDB2[(Redis DB 2 Blocklist Set)];
        M -- Updates --> MetricsStore;
        M -- Sends Alerts --> P{"Alert Dispatcher"};
        P -- Configured Method --> Q[External Systems: Slack, Email, SIEM, Fail2ban...];
    end

    subgraph "Monitoring"
        MetricsStore -- Provides Data --> MetricsEndpoint["/admin/metrics Endpoint"];
        Y(Admin UI - Flask) -- Fetches --> MetricsEndpoint;
        Y --> Z[Admin Dashboard];
    end

    subgraph "Background & Training Tasks"
        R -- Read By --> S(RF Training Script rag/training.py);
        S -- Trains --> T[Random Forest Model];
        T -- Saves --> U["./models/*.joblib"];

        Corpus["Text Corpus File"] -- Read By --> MarkovTrain(Markov Training Script rag/train_markov_postgres.py);
        MarkovTrain -- Populates --> PGDB;

        V(Archive Rotator - Scheduled) -- Manages --> W["./archives ZIPs"];
    end

    %% Styling (Optional)
    classDef nginx fill:#f9f,stroke:#333,stroke-width:2px;
    classDef api fill:#ccf,stroke:#333,stroke-width:1px;
    classDef redis fill:#ff9,stroke:#333,stroke-width:1px;
    classDef postgres fill:#e6f0ff,stroke:#333,stroke-width:1px;
    classDef storage fill:#eee,stroke:#333,stroke-width:1px;
    classDef task fill:#cfc,stroke:#333,stroke-width:1px;
    classDef external fill:#fcc,stroke:#333,stroke-width:1px;

    class B nginx;
    class H,L,M,Y api;
    class RedisDB1,RedisDB2,RedisDB3,RedisDB4 redis;
    class PGDB postgres;
    class R,U,W,Corpus storage;
    class S,V,MarkovTrain task;
    class Q external;
