# System Architecture

This document provides a high-level overview of how the components in the AI Scraping Defense Stack interact.

---

## 🧱 Component Overview & Data Flow

The system employs a layered and automated approach:

1. **Dynamic Configuration Update (Kubernetes CronJobs - Background):**
    * **Robots.txt Fetcher (`robots-fetcher-cronjob.yaml`):** Periodically runs `util/robots_fetcher.py`. This script fetches `/robots.txt` from the `REAL_BACKEND_HOST` (your actual application). The fetched content is stored in a Kubernetes ConfigMap (`live-robots-txt-config`).
    * **Wikipedia Corpus Updater (`corpus-updater-cronjob.yaml`):** Periodically runs `util/corpus_wikipedia_updater.py`. This script fetches content from random Wikipedia pages and saves/appends it to a text file on a PersistentVolumeClaim (`corpus-data-pvc`).

2. **Edge Filtering (Nginx + Lua):** Incoming requests first hit Nginx.
    * Lua scripts (`check_blocklist.lua`, `detect_bot.lua`) perform initial checks:
        * **Blocklist Check:** IP is checked against the Redis blocklist (DB 2). Blocked IPs get a 403 response immediately.
        * **Heuristics & `robots.txt`:** Basic request heuristics (User-Agent, headers) are evaluated. For known benign bots, compliance with rules from the dynamically updated `live-robots-txt-config` (mounted into Nginx) is checked.
    * Requests deemed safe and compliant are proxied to the real backend application (defined by `REAL_BACKEND_HOST`).
    * Suspicious requests or benign bots violating `robots.txt` rules are internally redirected to the Tarpit API.

3. **Tarpit & Escalation:**
    * **Tarpit API (FastAPI - `tarpit-api-deployment.yaml`):** Receives redirected requests.
        * Logs the hit and flags the IP visit (Redis DB 1).
        * Checks a hop counter for the IP (Redis DB 4). If the configured limit (`TAR_PIT_MAX_HOPS`) is exceeded, it triggers an immediate block by adding the IP to Redis DB 2 and returns a 403.
        * If the hop limit is not exceeded, it sends request metadata to the Escalation Engine.
        * Generates deterministic fake page content (using Markov chains from PostgreSQL - see step 6) and links.
        * Streams the fake page slowly back to the client.
    * **Escalation Engine (FastAPI - `escalation-engine-deployment.yaml`):** Analyzes metadata from the Tarpit API.
        * Performs frequency analysis using Redis DB 3.
        * Applies heuristic scoring and runs a pre-trained Random Forest model (loaded from `models-pvc`).
        * Uses rules from the dynamically updated `live-robots-txt-config` for its analysis.
        * Optionally calls external IP reputation services or local/external classification APIs.
        * If the request is deemed malicious, it forwards details to the AI Service webhook.

4. **AI Service & Actions (FastAPI - `ai-service-deployment.yaml`):** Receives confirmed malicious request data.
    * Adds the offending IP address to the Redis blocklist (DB 2) with a configurable TTL.
    * Optionally reports the IP to configured community blocklists.
    * Dispatches alerts via configured methods (Slack, SMTP, Webhook).

5. **Monitoring & Background Tasks (Deployments):**
    * **Admin UI (Flask - `admin-ui-deployment.yaml`):** Fetches and displays real-time metrics.
    * **Archive Rotator (`archive-rotator-deployment.yaml`):** Periodically generates new JS ZIP honeypots and saves them to `archives-pvc`. Nginx serves these archives from the same PVC.

6. **Markov Model Training (Kubernetes CronJob - Background):**
    * **Markov Model Trainer (`markov-model-trainer.yaml`):** Periodically runs `rag/train_markov_postgres.py`. This script reads the updated corpus from `corpus-data-pvc` (populated by the Wikipedia updater) and (re)trains/populates the Markov chain data in the PostgreSQL database.

---

### Mermaid Diagram

```mermaid
flowchart TD
    subgraph "User Interaction & Edge"
        A["Web Clients or Bots"] -- HTTP/S Request --> B(NGINX Port 80/443);
        B -- Uses rules from --> LiveRobotsTxtConfigMap["ConfigMap (live-robots.txt)"];
        B -- Checks --> C{"Blocklist Check (Lua + Redis DB 2)"};
        C -- Blocked --> D[Return 403];
        C -- Not Blocked --> E{"Heuristic & robots.txt Check (Lua)"};
        E -- Passed (to REAL_BACKEND_HOST) --> G["Proxy Pass"];
        E -- Suspicious/Violating --> F["Internal Redirect /api/tarpit"];
    end

    subgraph "Real Application"
        G -- Proxied To --> RealApp["Your Web Application (REAL_BACKEND_HOST)"];
        RealApp -- Serves /robots.txt --> RobotsFetcherCronJob;
    end

    subgraph "Tarpit & Escalation Pipeline"
        F --> H(Tarpit API - FastAPI);
        H -- Logs Hit --> Logs["Runtime Logs"];
        H -- Flags IP --> RedisDB1[(Redis DB 1 Tarpit Flags)];
        H -- Reads/Updates Hop Count --> RedisDB4[(Redis DB 4 Hop Counts)];
        H -- Updates --> MetricsStore[(Metrics Store)];
        H -- Hop Limit Exceeded --> BLOCK[Add IP to Redis DB 2];
        BLOCK --> D;
        H -- Hop Limit OK, POST Metadata --> L(Escalation Engine - FastAPI);
        L -- Uses rules from --> LiveRobotsTxtConfigMap;
        H -- Reads Markov Chain --> PGDB[(PostgreSQL Markov DB)];

        L -- Uses/Updates --> RedisDB3[(Redis DB 3 Freq Tracking)];
        L -- Updates --> MetricsStore;
        L -- If Malicious --> M(AI Service - FastAPI);
    end

    subgraph "AI Service & Actions"
        M -- Adds IP --> RedisDB2[(Redis DB 2 Blocklist Set)];
        M -- Updates --> MetricsStore;
        M -- Sends Alerts --> P{"Alert Dispatcher"};
        P -- Configured Method --> Q[External Systems: Slack, Email, SIEM];
    end

    subgraph "Monitoring"
        MetricsStore -- Provides Data --> MetricsEndpoint["/admin/metrics Endpoint"];
        Y(Admin UI - Flask) -- Fetches --> MetricsEndpoint;
        Y --> Z[Admin Dashboard];
    end

    subgraph "Background & Training Tasks (Kubernetes CronJobs)"
        RobotsFetcherCronJob["Robots.txt Fetcher CronJob (util/robots_fetcher.py)"] -- Updates --> LiveRobotsTxtConfigMap;
        
        CorpusUpdaterCronJob["Wikipedia Corpus Updater CronJob (util/corpus_wikipedia_updater.py)"] -- Writes to --> CorpusPVC[("PVC (corpus-data-pvc) for Wikipedia Corpus")];
        
        MarkovTrainerCronJob["Markov Model Trainer CronJob (rag/train_markov_postgres.py)"] -- Reads from --> CorpusPVC;
        MarkovTrainerCronJob -- Populates/Updates --> PGDB;

        RFTraining["RF Training (rag/training.py - manual or future job)"] -- Reads --> Logs;
        RFTraining -- Saves --> ModelsPVC[("PVC (models-pvc) for ML Models")];
        L -- Loads model from --> ModelsPVC;

        ArchiveRotator["Archive Rotator (Deployment - tarpit/rotating_archive.py)"] -- Manages --> ArchivesPVC[("PVC (archives-pvc) for ZIP Archives")];
        B -- Serves archives from --> ArchivesPVC;
    end

    classDef cronjob fill:#cde,stroke:#333,stroke-width:1px;
    class RobotsFetcherCronJob,CorpusUpdaterCronJob,MarkovTrainerCronJob cronjob;
    classDef pvc fill:#ead,stroke:#333,stroke-width:1px;
    class CorpusPVC,ModelsPVC,ArchivesPVC pvc;
    classDef configmap fill:#fdc,stroke:#333,stroke-width:1px;
    class LiveRobotsTxtConfigMap configmap;
'''
