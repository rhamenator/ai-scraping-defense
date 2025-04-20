# Getting Started with the AI Scraping Defense Stack

This guide provides the steps needed to set up, configure, run, and perform basic tests on the AI Scraping Defense Stack using Docker Compose.

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

    ```bash
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
    * **Review Variables:** Examine the variables listed (e.g., `ALERT_METHOD`, `ALERT_EMAIL_TO`, `LOCAL_LLM_API_URL`, etc.). These correspond to the `environment:` sections in `docker-compose.yml`.
    * **Customize Values:** Change the values to match your desired configuration. For example:
        * To enable email alerts via SMTP:

            ```dotenv
            ALERT_METHOD=smtp
            ALERT_EMAIL_TO=your-alert-address@example.com
            ALERT_EMAIL_FROM=defense-stack@your-server.com
            ALERT_SMTP_HOST=smtp.yourprovider.com
            ALERT_SMTP_PORT=587
            ALERT_SMTP_USE_TLS=true
            ALERT_SMTP_USER=your-smtp-username
            # ALERT_SMTP_PASSWORD variable is NOT set here - use secrets!
            ```

        * To use a specific local LLM model served by Ollama running outside Docker on the host machine:

            ```dotenv
            LOCAL_LLM_API_URL=[http://host.docker.internal:11434/v1/chat/completions](http://host.docker.internal:11434/v1/chat/completions)
            LOCAL_LLM_MODEL=mistral:latest
            ```

    * **Secrets:** For sensitive values like `ALERT_SMTP_PASSWORD` or `EXTERNAL_CLASSIFICATION_API_KEY`, **do not put them directly in `.env`**. Leave them commented out or remove them from `.env` and use Docker Secrets instead (see next step).
    * **`.gitignore`:** The `.gitignore` file in the repository should already list `.env`. **Never commit your actual `.env` file to Git.**

5. **Set up Docker Secrets (Recommended for Production, Optional for Testing):**
    * For each secret needed (e.g., SMTP password, external API key):
        * Create a plain text file inside the `./secrets/` directory. The filename should match the *key* used in the `secrets:` block at the bottom of `docker-compose.yml` (e.g., `smtp_password.txt`, `external_api_key.txt`).
        * The file should contain *only* the secret value (no extra spaces or newlines).
        * Example:

            ```bash
            # Create the secrets directory if it doesn't exist
            mkdir -p secrets
            # Create the secret files
            echo "your_actual_smtp_password" > ./secrets/smtp_password.txt
            echo "your_actual_external_api_key" > ./secrets/external_api_key.txt
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

    *(Look for connection errors (e.g., Redis, LLM API) or startup issues)*

## 5. Basic Testing & Verification

1. **Access Admin UI:** Open `http://localhost/admin/` in your browser. You should see the dashboard, potentially with metrics starting at 0. (Use `https://localhost/admin/` if you configured HTTPS).
2. **Test Tarpit Trigger (Bad UA):**
    * From your terminal, send a request with a known bad User-Agent listed in `nginx/lua/detect_bot.lua`:

        ```bash
        curl -A "curl/7.68.0" http://localhost/some-random-page -v
        # Or use another bad UA like 'python-requests'
        # curl -A "python-requests/2.28.1" http://localhost/some-random-page -v
        ```

    * **Expected:** You should receive a slow-streaming HTML response (likely with "Please wait" or Markov-generated text).
        * Check Nginx logs (`docker-compose logs -f nginx`): Look for `[BOT DETECTED: ...]` messages from `detect_bot.lua`.
        * Check Tarpit API logs (`docker-compose logs -f tarpit_api`): Look for `TAR PIT HIT` messages.
        * Check Escalation Engine logs (`docker-compose logs -f escalation_engine`): Look for `Received escalation request` and subsequent analysis messages.
3. **Test Escalation & Blocklisting:**
    * Triggering the tarpit (as above) should cause the Escalation Engine to analyze the request. If the combined score is high enough or other triggers are met (e.g., "High Combined Score", "Local LLM Classification"), it should call the AI Service webhook (`/analyze`).
    * Check AI Service logs (`docker-compose logs -f ai_service`): Look for `Webhook Received`, `Processing complete`, and potentially `Action: ip_blocklisted`.
    * Check Redis: If `redis-cli` is installed, connect and check the blocklist set (DB 2 by default):

        ```bash
        redis-cli -n 2 SISMEMBER blocklist:ip <IP_ADDRESS_OF_CURL_MACHINE>
        ```

        *(Replace `<IP_ADDRESS_OF_CURL_MACHINE>` with the IP seen in the logs, likely your host machine's Docker bridge IP, e.g., `172.x.x.x`, or your public IP if testing from outside. The command should return `(integer) 1` if blocked).*
4. **Test Blocklist Enforcement:**
    * Immediately after confirming the IP is blocklisted in Redis (step 3), repeat the `curl` command from step 2.
    * **Expected:** You should now receive a `403 Forbidden` response directly from Nginx.
    * Check Nginx logs (`docker-compose logs -f nginx`): Look for messages from `check_blocklist.lua` indicating the block (`Blocking IP ... found in Redis set`).
5. **Test Alerting (If Configured):**
    * If you configured `ALERT_METHOD` and the necessary credentials/URLs in `.env` or secrets, check the target system (Slack channel, email inbox, generic webhook receiver) for an alert message after triggering the blocklist in step 3. Check `ai_service` logs for success/error messages related to sending alerts (`Slack alert sent successfully`, `SMTP error sending email alert`, etc.).

## 6. Running Training (Optional)

1. Ensure prerequisite data (`robots.txt`, Apache logs, optionally feedback logs) is in place (see Section 3).
2. Execute the training script inside the `escalation_engine` container (as it has the necessary dependencies and volume mounts defined in `docker-compose.yml`).

    ```bash
    # Run the training script in a one-off container
    docker-compose run --rm escalation_engine python rag/training.py
    ```

    *(The `--rm` flag removes the container after the script finishes)*
3. **Expected Output:** The script will print progress messages for DB setup, log parsing, labeling, feature extraction, model training/evaluation, and saving the model (`.joblib`) and fine-tuning data (`.jsonl`) to the respective volume mounts (`./models`, `./data/finetuning_data`). Check these host directories for the output files.

## 7. Production Considerations

Deploying this stack in production requires additional steps beyond basic testing:

* **HTTPS:** **Crucial.** Configure Nginx with valid SSL/TLS certificates (e.g., using Let's Encrypt/Certbot). Uncomment and configure the SSL sections in `nginx.conf` and ensure certificates and the `dhparam.pem` file are mounted correctly in `docker-compose.yml`. Enable HSTS headers once HTTPS is confirmed working. Redirect HTTP traffic to HTTPS.
* **Secrets Management:** **Mandatory.** Use Docker secrets (as outlined in Step 2.5) or a dedicated secrets management solution (like HashiCorp Vault) for all API keys, passwords, and sensitive configuration. **Never commit secrets to Git.**
* **Resource Allocation:** Monitor the CPU and memory usage of each container under load (`docker stats`). Adjust the `deploy.resources.limits` in `docker-compose.yml` accordingly to prevent resource exhaustion and ensure stability. The Escalation Engine and Tarpit API might need more resources depending on traffic and analysis complexity. Increase Nginx `worker_connections` if needed.
* **Monitoring & Logging:**
  * Set up external monitoring for container health, resource usage, and API response times (e.g., using Prometheus/Grafana, Datadog). Consider exposing application-specific metrics via Prometheus exporters if needed.
  * Configure log aggregation (e.g., ELK stack, Loki, Promtail) to centralize logs from all containers for easier analysis and troubleshooting.
  * Implement log rotation for Nginx and application logs within the containers or on the host volume mounts to prevent disks from filling up (e.g., using `logrotate`).
* **Database:** For high-traffic sites, the SQLite database used by `training.py` might become a bottleneck during the training process. Consider migrating to a more robust database like PostgreSQL for log storage and analysis if training performance becomes an issue. The runtime system primarily uses Redis.
* **Firewall:** Configure host firewall rules (e.g., `ufw`, `firewalld`) to only expose necessary ports (typically 80 and 443 via Nginx). Restrict direct access to backend service ports.
* **Backups:** Implement a strategy for backing up persistent data (Redis data volume, generated models, configuration files, certificates).
* **Updates:** Regularly update base Docker images, OS packages within containers, and Python dependencies (`requirements.txt`) to patch security vulnerabilities. Use tools like Dependabot or `pip-audit`.
* **Fail2ban/CrowdSec:** Consider integrating the blocklist events (e.g., from `ai_service` logs or webhook alerts) with tools like Fail2ban or CrowdSec to implement firewall-level blocking for persistent offenders, reducing load on Nginx/Redis.

## 8. Stopping the Stack

```bash
docker-compose down
(This stops and removes the containers and network, but preserves named volumes like redis_data by default)To stop containers AND remove named volumes (like Redis data):docker-compose down -v
This guide should provide a solid starting point for setting up and testing the core functionality of the system. Remember to adapt paths and configurations based on your specific environment and needs
