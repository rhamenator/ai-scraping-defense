# API References

This document provides details on the APIs exposed by the different services within the AI Scraping Defense Stack.

---

## 1. Nginx

* **Role:** Reverse Proxy, Edge Filtering, serving Admin UI and static assets.
* **Exposed Ports (Defaults in Docker Compose):** 80 (HTTP), 443 (HTTPS). In Kubernetes, this depends on the Nginx Service type (e.g., LoadBalancer, NodePort) or Ingress configuration.
* **Key Internal Locations & Proxied Services:**
  * `/` (Default): Proxies to the real backend application (defined by `REAL_BACKEND_HOST`) after passing Lua checks.
  * `/admin/`: Proxies to the Admin UI service (`admin_ui` on port 5002 internally).
  * `/api/tarpit`: **Internal location.** Requests are redirected here by `detect_bot.lua` for suspicious traffic. Proxies to the Tarpit API service (`tarpit_api` on port 8001 internally).
  * `/docs/archives/`: Serves static ZIP files generated by the Archive Rotator from the `/usr/share/nginx/html/archives/` path.

---

## 2. Tarpit API (`tarpit_api.py`)

* **Role:** Handle suspicious requests, slow down bots, generate fake content, escalate metadata.
* **Default Internal Port:** 8001 (Docker Compose & Kubernetes)
* **Framework:** FastAPI
* **Endpoints:**
  * **`GET /tarpit/{path:path}`**
    * **Description:** Main tarpit endpoint accessed via internal Nginx redirect. Logs the hit, flags the IP (Redis DB 1), checks the hop limit (Redis DB 4), escalates metadata to the Escalation Engine, generates deterministic fake content using PostgreSQL, and streams the response slowly.
    * **Path Parameter:** `path` captures the original path requested by the client.
    * **Responses:**
      * `200 OK`: Streams HTML content slowly. Content is deterministically generated based on path hash and system seed.
      * `403 Forbidden`: Returned immediately (non-streaming) if the client IP exceeds the configured `TAR_PIT_MAX_HOPS` limit within the `TAR_PIT_HOP_WINDOW_SECONDS` window. The IP is also added to the blocklist (Redis DB 2).
    * **Authentication:** None (accessed internally via Nginx).
  * **`GET /health`**
    * **Description:** Basic health check endpoint. Verifies Redis connectivity for hops and blocklist DBs, and Tarpit configuration.
    * **Responses:** `200 OK` with JSON status (e.g., `{"status": "ok", "generator_available": true, "postgres_connected": true, "redis_hops_connected": true, "redis_blocklist_connected": true, "hop_limit_enabled": true, "max_hops_config": 250}`).
    * **Authentication:** None.
  * **`GET /`**
    * **Description:** Root endpoint providing basic service info.
    * **Responses:** `200 OK` with JSON message (e.g., `{"message": "AntiScrape Tarpit API"}`).
    * **Authentication:** None.

---

## 3. Escalation Engine (`escalation_engine.py`)

* **Role:** Analyze suspicious request metadata, score requests, trigger further actions.
* **Default Internal Port:** 8003 (Docker Compose & Kubernetes)
* **Framework:** FastAPI
* **Endpoints:**
  * **`POST /escalate`**
    * **Description:** Receives request metadata (typically from the Tarpit API). Performs frequency analysis (Redis DB 3), heuristic checks, runs the Random Forest model, and optionally calls external APIs (IP reputation, LLM, etc.). If deemed malicious, forwards data to the AI Service webhook.
    * **Request Body (JSON):** `RequestMetadata` model. Example:

      ```json
      {
        "timestamp": "2023-10-27T10:30:00Z",
        "ip": "192.0.2.1",
        "user_agent": "SuspiciousBot/1.0",
        "referer": "[http://example.com/forbidden-page](http://example.com/forbidden-page)",
        "path": "/tarpit/some/fake/resource.html",
        "headers": {"X-Custom-Header": "value"},
        "source": "tarpit_api"
      }
      ```

    * **Responses:**
      * `200 OK`: Successfully processed the request. JSON response includes `{"status": "processed", "action_taken": "...", "is_bot_decision": true/false/null, "score": 0.xx}`.
      * `422 Unprocessable Entity`: Invalid request body format.
      * `500 Internal Server Error`: Internal error during processing.
    * **Authentication:** None (intended for internal calls).
  * **`GET /health`**
    * **Description:** Basic health check endpoint. Verifies Redis connectivity for frequency tracking and model loading status.
    * **Responses:** `200 OK` with JSON status (e.g., `{"status": "ok", "redis_frequency_connected": true, "model_loaded": true}`).
    * **Authentication:** None.
  * **`GET /metrics`**
    * **Description:** Returns current internal metrics specific to the Escalation Engine (from its own instance of the shared `metrics` module).
    * **Responses:** `200 OK` with JSON containing metrics.
    * **Authentication:** None.
  * **`GET /`**
    * **Description:** Root endpoint providing basic service info.
    * **Responses:** `200 OK` with JSON message (e.g., `{"message": "Escalation Engine"}`).
    * **Authentication:** None.

---

## 4. AI Service (`ai_service/ai_webhook.py`)

* **Role:** Manage blocklist, dispatch alerts, optionally report to community lists.
* **Default Internal Port:** 8000 (Docker Compose & Kubernetes)
* **Framework:** FastAPI
* **Endpoints:**
  * **`POST /analyze`**
    * **Description:** Receives webhook data (typically for confirmed malicious requests from the Escalation Engine). Adds the source IP to the Redis blocklist (DB 2) with TTL and triggers configured alerts/reporting.
    * **Request Body (JSON):** `WebhookEvent` model. Example:

      ```json
      {
        "event_type": "suspicious_activity_detected",
        "reason": "High Combined Score (0.95)",
        "timestamp_utc": "2023-10-27T10:35:00Z",
        "details": {
          "ip": "192.0.2.1",
          "user_agent": "SuspiciousBot/1.0",
          "path": "/tarpit/some/fake/resource.html",
          "score": 0.95
        }
      }
      ```

    * **Responses:**
      * `202 Accepted`: Webhook received and accepted for processing. JSON response includes `{"status": "processed", "action_taken": "...", "ip_processed": "..."}`.
      * `422 Unprocessable Entity`: Invalid request body format.
      * `5xx Server Error`: Internal error during processing.
    * **Authentication:** None (intended for internal calls).
  * **`GET /health`**
    * **Description:** Basic health check endpoint. Verifies Redis connectivity for blocklisting.
    * **Responses:** `200 OK` with JSON status (e.g., `{"status": "ok", "redis_blocklist_connected": true}`).
    * **Authentication:** None.
  * **`GET /`**
    * **Description:** Root endpoint providing basic service info.
    * **Responses:** `200 OK` with JSON message (e.g., `{"message": "AI Defense Webhook Service"}`).
    * **Authentication:** None.

---

## 5. Admin UI (`admin_ui/admin_ui.py`)

* **Role:** Display real-time system metrics aggregated from various services.
* **Default Internal Port:** 5002 (Docker Compose & Kubernetes)
* **Framework:** Flask
* **Endpoints (accessed via Nginx reverse proxy):**
  * **`GET /admin/`** (External path proxied by Nginx to `/` of Admin UI service)
    * **Description:** Serves the HTML dashboard page.
    * **Responses:** `200 OK` (HTML content).
    * **Authentication:** None by default (consider adding auth via Nginx for production).
  * **`GET /admin/metrics`** (External path proxied by Nginx to `/metrics` of Admin UI service)
    * **Description:** Returns current aggregated metrics data as JSON. Fetched by the dashboard's JavaScript.
    * **Responses:** `200 OK` (JSON containing metrics from the shared `metrics.py` module).
    * **Authentication:** None by default.

---
