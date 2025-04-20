# Getting Started with the AI Scraping Defense Stack

This guide provides the steps needed to set up, configure, run, and perform basic tests on the AI Scraping Defense Stack using **Docker Compose**.

For deployment using Kubernetes (recommended for production environments), please refer to the [Kubernetes Deployment Guide](kubernetes_deployment.md).

## 1. Prerequisites

Ensure you have the following installed on your system:

* **Docker:** The containerization platform. ([Install Docker](https://docs.docker.com/engine/install/))
* **Docker Compose:** Tool for defining and running multi-container Docker applications (usually included with Docker Desktop, otherwise install separately: [Install Docker Compose](https://docs.docker.com/compose/install/))
* **Git:** For cloning the repository. ([Install Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git))
* **(Optional) `redis-cli`:** Useful for verifying the blocklist directly in Redis.
* **(Optional) `curl`:** Useful for sending test HTTP requests.

## 2. Setup & Configuration

1. **Clone the Repository:**

    ```bash
    git clone [https://github.com/rhamenator/ai-scraping-defense.git](https://github.com/rhamenator/ai-scraping-defense.git)
    cd ai-scraping-defense
    ```

2. **Create Configuration & Data Directories:**
    Ensure the following directories exist in the project root. Docker Compose volumes rely on these host paths.

    ```bash
    mkdir -p config data logs models archives secrets nginx/errors certs
    ```

    * `config/`: For `robots.txt` and potentially other static configs.
    * `data/`: For training data (`apache_access.log`), generated data (`log_analysis.db`, `finetuning_data/`).
    * `logs/`: For application and Nginx logs.
    * `models/`: For the trained ML model (`.joblib`).
    * `archives/`: For generated JS ZIP honeypots.
    * `secrets/`: **IMPORTANT:** For storing sensitive data files (API keys, passwords). **Add `secrets/` to your `.gitignore` file!**
    * `nginx/errors`: For custom Nginx error pages (optional).
    * `certs`: For SSL/TLS certificates and keys (required for HTTPS).

3. **Create `robots.txt`:**
    Place your website's `robots.txt` file inside the `config/` directory:

    ```plaintext
    ./config/robots.txt
    ```

    The training script (`rag/training.py`) and potentially other components rely on this path. A restrictive example:

    ```robots.txt
    User-agent: *
    Disallow: /admin/
    Disallow: /api/
    Disallow: /tarpit/
    Disallow: /config/
    Disallow: /models/
    Disallow: /secrets/
    Disallow: /data/
    Disallow: /cgi-bin/

    User-agent: GPTBot
    Disallow: /

    User-agent: CCBot
    Disallow: /

    # Add other specific bot disallows here
    ```

4. **Create `.env` File (Environment Variables):**
    The `docker-compose.yml` file reads environment variables from a file named `.env` in the project root to configure services.
    * **Use the Sample:** A `sample.env` file is provided in the repository. Copy it to create your `.env` file:

        ```bash
        cp sample.env .env
        ```

    * **Edit `.env`:** Open the newly created `.env` file in a text editor.
    * **Review Variables:** Examine the variables listed. These correspond to the `environment:` sections in `docker-compose.yml`.
    * **Customize Values:** Change the values to match your desired configuration. Key sections include:
        * **Alerting (`ai_service`):** Configure `ALERT_METHOD`, `ALERT_EMAIL_TO`, `ALERT_SMTP_HOST`, etc. Remember the SMTP password comes from a secret file.
        * **LLM/External APIs (`escalation_engine`):** Set `LOCAL_LLM_API_URL`, `LOCAL_LLM_MODEL`, `EXTERNAL_CLASSIFICATION_API_URL` if using these features. API keys come from secret files.
        * **IP Reputation (`escalation_engine` - NEW):**
            * `ENABLE_IP_REPUTATION=true` (to enable)
            * `IP_REPUTATION_API_URL=https://api.example-ip-rep.com/v1/lookup` (Set the correct URL for your chosen service)
            * `IP_REPUTATION_TIMEOUT=10.0`
            * `IP_REPUTATION_MALICIOUS_SCORE_BONUS=0.3` (How much to increase suspicion score if IP is flagged)
            * `IP_REPUTATION_MIN_MALICIOUS_THRESHOLD=50` (Service-specific score threshold, e.g., for AbuseIPDB)
            * API key comes from a secret file (`IP_REPUTATION_API_KEY_FILE`).
        * **CAPTCHA Trigger (`escalation_engine` - NEW Hooks):**
            * `ENABLE_CAPTCHA_TRIGGER=true` (to enable the *logging* that a CAPTCHA would be triggered - requires separate frontend/backend implementation for the actual challenge)
            * `CAPTCHA_SCORE_THRESHOLD_LOW=0.2` (Trigger if score is above this...)
            * `CAPTCHA_SCORE_THRESHOLD_HIGH=0.5` (...and below this)
            * `CAPTCHA_VERIFICATION_URL=/verify-captcha` (Example path where your app would handle the challenge)
        * **Community Reporting (`ai_service` - NEW):**
            * `ENABLE_COMMUNITY_REPORTING=true` (to enable reporting blocked IPs)
            * `COMMUNITY_BLOCKLIST_REPORT_URL=https://api.abuseipdb.com/api/v2/report` (Example: AbuseIPDB endpoint)
            * `COMMUNITY_BLOCKLIST_REPORT_TIMEOUT=10.0`
            * API key comes from a secret file (`COMMUNITY_BLOCKLIST_API_KEY_FILE`).
    * **Secrets:** For sensitive values (`ALERT_SMTP_PASSWORD`, `EXTERNAL_CLASSIFICATION_API_KEY`, `IP_REPUTATION_API_KEY`, `COMMUNITY_BLOCKLIST_API_KEY`), **do not put them directly in `.env`**. Use Docker Secrets (see next step).
    * **`.gitignore`:** The `.gitignore` file in the repository should already list `.env`. **Never commit your actual `.env` file to Git.**

5. **Set up Docker Secrets (Recommended for Production, Optional for Testing):**
    * For each secret needed (SMTP password, external API key, IP reputation key, community reporting key):
        * Create a plain text file inside the `./secrets/` directory. The filename should match the *key* used in the `secrets:` block at the bottom of `docker-compose.yml` (e.g., `smtp_password.txt`, `external_api_key.txt`, `ip_reputation_api_key.txt`, `community_blocklist_api_key.txt`).
        * The file should contain *only* the secret value (no extra spaces or newlines).
        * Example:

            ```bash
            # Create the secrets directory if it doesn't exist
            mkdir -p secrets
            # Create the secret files
            echo "your_actual_smtp_password" > ./secrets/smtp_password.txt
            echo "your_actual_external_api_key" > ./secrets/external_api_key.txt
            echo "your_ip_reputation_service_key" > ./secrets/ip_reputation_api_key.txt
            echo "your_community_reporting_api_key" > ./secrets/community_blocklist_api_key.txt
            # Ensure secrets directory is ignored by Git
            echo "/secrets/" >> .gitignore
            ```

    * The application code (e.g., `ai_service/ai_webhook.py`, `escalation/escalation_engine.py`) is configured to read secrets from the standard Docker path `/run/secrets/<secret_name>` (e.g., `/run/secrets/smtp_password`).

## 3. Data Setup (Optional - Needed for Training)

If you plan to run the ML model training script (`rag/training.py`):

1. **Place Apache Log File:** Copy a sample (or full) Apache access log file (Combined Log Format is expected) into the `./data/` directory. Ensure its name matches the `TRAINING_LOG_FILE_PATH` environment variable used by the training script (default: `/app/data/apache_access.log` inside the container, which maps to `./data/apache_access.log` on the host).
2. **Create Placeholder Feedback Logs:** If you don't have real feedback data yet but want `training.py` to run without file-not-found errors, create empty placeholder files:

    ```bash
    touch ./logs/honeypot_hits.log
    touch ./logs/captcha_success.log
    ```

    *(Note: The training script will load empty sets from these files. Initial labeling quality will depend entirely on heuristics until real feedback data is generated).*

## 4. Build and Run the Stack

1. **Build Docker Images:**

    ```bash
    docker-compose build
    ```

    *(This might take some time on the first run)*
2. **Start Services:**

    ```bash
    docker-compose up -d
    ```

    *(The `-d` runs containers in detached mode)*
3. **Check Container Status:**

    ```bash
    docker-compose ps
    ```

    *(Ensure all services listed in `docker-compose.yml` are `Up` or `Running`)*
4. **View Logs (Optional):**

    ```bash
    docker-compose logs -f          # View logs from all services (use Ctrl+C to stop)
    docker-compose logs -f nginx    # View logs for a specific service
    docker-compose logs -f escalation_engine
    docker-compose logs -f ai_service
    ```

    *(Look for connection errors (e.g., Redis, LLM API, IP Reputation API) or startup issues)*

## 5. Basic Testing & Verification

1. **Access Admin UI:** Open `http://localhost/admin/` in your browser. You should see the dashboard, potentially with metrics starting at 0. (Use `https://localhost/admin/` if you configured HTTPS).
2. **Test Tarpit Trigger (Bad UA):**
    * From your terminal, send a request with a known bad User-Agent listed in `nginx/lua/detect_bot.lua`:

        ```bash
        curl -A "curl/7.68.0" http://localhost/some-random-page -v
        ```

    * **Expected:** Slow-streaming HTML response. Check logs (`nginx`, `tarpit_api`, `escalation_engine`) for detection messages.
3. **Test Escalation & Blocklisting:**
    * Triggering the tarpit should lead to analysis by the Escalation Engine. If IP Reputation is enabled, check logs for `Checking IP reputation...`. If the score is high enough, it calls the AI Service.
    * Check AI Service logs (`docker-compose logs -f ai_service`): Look for `Webhook Received`, `Processing complete`, and potentially `Action: ip_blocklisted`. If Community Reporting is enabled, look for `Reporting IP ... to community blocklist`.
    * Check Redis (`redis-cli -n 2 SISMEMBER blocklist:ip <IP>`) to confirm blocklisting.
4. **Test Blocklist Enforcement:**
    * Repeat the `curl` command after confirming the IP is blocklisted.
    * **Expected:** `403 Forbidden` response from Nginx. Check Nginx logs for `check_blocklist.lua` messages.
5. **Test Alerting (If Configured):**
    * Check the configured target (Slack, email, webhook) for an alert after blocklisting. Check `ai_service` logs for alert sending status.

## 6. Running Training (Optional)

1. Ensure prerequisite data (`robots.txt`, Apache logs, optionally feedback logs) is in place (see Section 3).
2. Execute the training script inside the `escalation_engine` container:

    ```bash
    docker-compose run --rm escalation_engine python rag/training.py
    ```

3. **Expected Output:** Progress messages and saved model (`.joblib`) and fine-tuning data (`.jsonl`) in `./models` and `./data/finetuning_data` host directories.

## 7. Production Considerations

Deploying this stack in production requires additional steps beyond basic testing:

* **HTTPS:** **Crucial.** Configure Nginx with valid SSL/TLS certificates and `dhparam.pem`. Enable HSTS. Redirect HTTP to HTTPS.
* **Secrets Management:** **Mandatory.** Use Docker secrets or a dedicated secrets management solution for all sensitive configuration.
* **Resource Allocation:** Monitor CPU/memory (`docker stats`) and adjust `deploy.resources.limits` in `docker-compose.yml`.
* **Monitoring & Logging:** Set up external monitoring (Prometheus/Grafana, etc.) and centralized log aggregation (ELK, Loki). Implement log rotation.
* **IP Reputation & Community APIs:** Ensure you understand the terms of service, rate limits, and costs associated with any third-party APIs used for IP reputation or blocklist reporting. Adapt the parsing logic in `escalation_engine.py` and `ai_service.py` for the specific APIs you choose.
* **CAPTCHA Implementation:** If `ENABLE_CAPTCHA_TRIGGER` is true, you need to build the corresponding frontend and backend logic in your main web application (`I` in the diagram) to actually present and verify the CAPTCHA challenge when indicated by the Escalation Engine (this requires coordination beyond the scope of this stack alone).
* **Database:** Consider PostgreSQL for `training.py` if SQLite becomes too slow for large log volumes.
* **Firewall:** Configure host firewall rules (e.g., `ufw`, `firewalld`) to expose only necessary ports (80, 443).
* **Backups:** Implement backups for persistent data (Redis volume, models, configs, certs).
* **Updates:** Regularly update base images, OS packages, and Python dependencies.
