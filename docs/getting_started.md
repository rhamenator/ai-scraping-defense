# Getting Started with the AI Scraping Defense Stack

This guide provides the steps needed to set up, configure, run, and perform basic tests on the AI Scraping Defense Stack using **Docker Compose**.

For deployment using Kubernetes (recommended for production environments), please refer to the [Kubernetes Deployment Guide](kubernetes_deployment.md).

## 1. Prerequisites

Ensure you have the following installed on your system:

* **Docker:** The containerization platform. ([Install Docker](https://docs.docker.com/engine/install/))
* **Docker Compose:** Tool for defining and running multi-container Docker applications (usually included with Docker Desktop, otherwise install separately: [Install Docker Compose](https://docs.docker.com/compose/install/))
* **Git:** For cloning the repository. ([Install Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git))
* **PostgreSQL Client (`psql`):** Useful for verifying the Markov database setup (Optional, but recommended if managing the DB directly).
* **Text Editor:** For editing configuration files.
* **(Optional) `redis-cli`:** Useful for verifying the blocklist and other Redis data directly.
* **(Optional) `curl`:** Useful for sending test HTTP requests.

## 2. Setup & Configuration

1.  **Clone the Repository:**

    ```bash
    git clone [https://github.com/your-username/ai-scraping-defense.git](https://github.com/your-username/ai-scraping-defense.git) # Replace with your repo URL
    cd ai-scraping-defense
    ```

2.  **Create Configuration & Data Directories:**
    Ensure the following directories exist in the project root. Docker Compose volumes rely on these host paths.

    ```bash
    mkdir -p config data logs models archives secrets nginx/errors certs db
    ```

    * `config/`: For `robots.txt` and potentially other static configs.
    * `data/`: For training data (e.g., `apache_access.log`), corpus files for Markov training.
    * `db/`: To potentially hold database initialization scripts (like `init_markov.sql`).
    * `logs/`: For application and Nginx logs.
    * `models/`: For the trained ML model (`.joblib`).
    * `archives/`: For generated JS ZIP honeypots.
    * `secrets/`: **IMPORTANT:** For storing sensitive data files (API keys, passwords). **Add `secrets/` to your `.gitignore` file!**
    * `nginx/errors`: For custom Nginx error pages (optional).
    * `certs`: For SSL/TLS certificates and keys (required for HTTPS).

3.  **Create `robots.txt`:**
    Place your website's `robots.txt` file inside the `config/` directory:

    ```plaintext
    ./config/robots.txt
    ```

    This file is used by the Nginx Lua script (`detect_bot.lua`) to check rules for benign bots and potentially by the training script (`rag/training.py`). A restrictive example:

    ```robots.txt
    # Allow general crawlers some access
    User-agent: *
    Disallow: /admin/
    Disallow: /api/
    Disallow: /tarpit/ # Explicitly disallow tarpit if desired
    Disallow: /config/
    Disallow: /models/
    Disallow: /secrets/
    Disallow: /data/
    Disallow: /cgi-bin/
    Disallow: /search # Example: disallow internal search

    # Block common scrapers/AI bots completely
    User-agent: GPTBot
    Disallow: /

    User-agent: CCBot
    Disallow: /

    User-agent: Bytespider
    Disallow: /

    # Add other specific bot disallows here
    ```

4.  **Prepare PostgreSQL Database:**
    * The Tarpit API now requires a PostgreSQL database to store its Markov chain data.
    * The included `docker-compose.yml` sets up a PostgreSQL service.
    * **Schema Initialization:** You need to ensure the necessary tables (`markov_words`, `markov_sequences`) are created.
        * You can place the `db/init_markov.sql` script (provided in a previous response) in the `./db/` directory.
        * Uncomment the volume mount line for `init.sql` in the `postgres` service definition within `docker-compose.yml` to have Docker run it automatically on the first startup of an empty database volume:
            ```diff
            # anti_scrape/docker-compose.yml
            services:
              postgres:
                # ... other settings ...
                volumes:
                  - postgres_data:/var/lib/postgresql/data
                  # Optional: Mount init script for schema creation
            +     - ./db/init_markov.sql:/docker-entrypoint-initdb.d/init.sql
                # ... other settings ...
            ```
        * Alternatively, connect to the database manually after starting the stack (using `psql` or another tool) and run the contents of `init_markov.sql`.

5.  **Prepare Markov Training Corpus:**
    * Place the text file(s) you want to use to train the Markov generator into the `./data/` directory (or another location accessible for the training script). This could be documentation text, scraped web content, etc.
    * A larger, more coherent corpus will result in more plausible fake text from the tarpit.

6.  **Create `.env` File (Environment Variables):**
    * Copy the `sample.env` file to `.env`:

        ```bash
        cp sample.env .env
        ```

    * **Edit `.env`:** Open `.env` and customize values. Pay attention to:
        * **PostgreSQL Settings:** Ensure these match the `postgres` service in `docker-compose.yml` (or your external DB).
            * `PG_HOST=postgres`
            * `PG_PORT=5432`
            * `PG_DBNAME=markovdb`
            * `PG_USER=markovuser`
            * (Password comes from a secret file)
        * **Tarpit Settings:**
            * `SYSTEM_SEED`: **IMPORTANT:** Change this to a unique, random string.
            * `TAR_PIT_MAX_HOPS=250` (Adjust max requests per IP, 0 to disable)
            * `TAR_PIT_HOP_WINDOW_SECONDS=86400` (Time window for hop count)
            * `REDIS_DB_TAR_PIT_HOPS=4` (Redis DB for hop counts)
            * `TAR_PIT_MIN_DELAY_SEC=0.6`
            * `TAR_PIT_MAX_DELAY_SEC=1.2`
            * `TAR_PIT_FLAG_TTL=300`
            * `REDIS_DB_TAR_PIT=1` (Redis DB for visit flags)
        * **Deployment Mode:**
            * `REAL_BACKEND_HOST=http://your-real-app-service:8080` **IMPORTANT:** Set this to the actual address (hostname/IP and port) of your *real* web application backend IF you are running the anti-scrape stack separately. If running co-located where Nginx can directly serve/proxy, this might point to localhost or another internal address.
        * **Redis Settings:**
            * `REDIS_HOST=redis`
            * `REDIS_PORT=6379`
            * `REDIS_DB_BLOCKLIST=2`
            * `REDIS_DB_FREQUENCY=3`
            * (Password comes from a secret file)
        * **Alerting, External APIs, etc.:** Configure as needed.

7.  **Set up Docker Secrets:**
    * Create plain text files inside the `./secrets/` directory for:
        * `pg_password.txt`: Contains the password for the `PG_USER`.
        * `redis_password.txt`: (Optional) Contains the Redis password if Redis requires auth.
        * `smtp_password.txt`
        * `external_api_key.txt`
        * `ip_reputation_api_key.txt`
        * `community_blocklist_api_key.txt`
    * Example:

        ```bash
        mkdir -p secrets
        echo "your_secure_pg_password" > ./secrets/pg_password.txt
        # echo "your_secure_redis_password" > ./secrets/redis_password.txt # If using Redis auth
        # ... create other secret files ...
        echo "/secrets/" >> .gitignore # Ensure secrets are not committed
        ```

## 3. Data Setup (ML Training & Markov Corpus)

* **ML Training Data:** If running `rag/training.py`, place your Apache log file in `./data/` and optionally create empty feedback logs (`./logs/honeypot_hits.log`, `./logs/captcha_success.log`).
* **Markov Corpus:** Ensure your text corpus file(s) are ready (e.g., in `./data/`) for the Markov training step (see Section 5).

## 4. Build and Run the Stack

1.  **Build Docker Images:**

    ```bash
    docker-compose build
    ```

2.  **Start Services:**

    ```bash
    docker-compose up -d
    ```

3.  **Check Container Status:**

    ```bash
    docker-compose ps
    ```

    *(Ensure `postgres`, `redis`, `nginx`, `tarpit_api`, etc., are `Up`)*
4.  **View Logs (Optional):**

    ```bash
    docker-compose logs -f          # View all logs
    docker-compose logs -f postgres # Check PostgreSQL startup
    docker-compose logs -f tarpit_api # Check Tarpit API startup & DB/Redis connections
    ```

## 5. Train Markov Model (Required for Tarpit Content)

* After the stack is running (especially the `postgres` service), run the Markov training script. You need to execute this *inside* a container that has the Python environment and can connect to the database. The `tarpit_api` container is suitable.
* Replace `data/your_corpus.txt` with the actual path *relative to the project root* of your corpus file.

    ```bash
    docker-compose run --rm tarpit_api python rag/train_markov_postgres.py /app/data/your_corpus.txt
    ```
    *(Note: `/app/data/` inside the container maps to `./data/` on the host).*
* This might take some time depending on the corpus size. Monitor the logs for progress.

## 6. Basic Testing & Verification

1.  **Access Admin UI:** Open `http://localhost/admin/`.
2.  **Test Tarpit Trigger (Bad UA):**

    ```bash
    curl -A "curl/7.68.0" http://localhost/some-random-page -v
    ```
    * **Expected:** Slow-streaming HTML response containing generated text. Check `tarpit_api` logs for "Seeded RNG..." messages and potential DB queries.
3.  **Test Hop Limit (Requires `TAR_PIT_MAX_HOPS` > 0):**
    * Repeat the `curl` command above `TAR_PIT_MAX_HOPS + 1` times.
    * **Expected:** On the request *after* the limit is hit, you should receive an immediate `403 Forbidden` response. Check `tarpit_api` logs for "Tarpit hop limit exceeded" and "BLOCKED IP" messages. Check Redis DB 2 for the block (`redis-cli -n 2 GET blocklist:<Your IP>`).
4.  **Test Benign Bot + `robots.txt` Violation:**
    * Find a path disallowed in your `./config/robots.txt` (e.g., `/admin/`).
    * Send a request spoofing Googlebot to that path:

        ```bash
        curl -A "Mozilla/5.0 (compatible; Googlebot/2.1; +[http://www.google.com/bot.html](http://www.google.com/bot.html))" http://localhost/admin/ -v
        ```
    * **Expected:** Slow-streaming HTML response from the tarpit (as the benign bot violated rules). Check `nginx` logs for `detect_bot.lua` messages indicating a benign bot accessed a disallowed path.
5.  **Test Legitimate Request:**
    * Access `http://localhost/` (or another allowed path) in your browser or with a standard `curl` request.
    * **Expected:** The response from your *real* backend application (proxied via `REAL_BACKEND_HOST`). If `REAL_BACKEND_HOST` is not configured or pointing to a non-running service, you might get a 502 Bad Gateway from Nginx.
6.  **Test Escalation & Blocklisting:** (Trigger tarpit multiple times if needed to increase suspicion score). Check `escalation_engine` and `ai_service` logs, and Redis DB 2.
7.  **Test Alerting:** Check configured alert targets.

## 7. Running ML Training (Optional)

1.  Ensure prerequisite data is in place.
2.  Execute the training script:

    ```bash
    docker-compose run --rm escalation_engine python rag/training.py
    ```

## 8. Production Considerations

* **HTTPS:** Mandatory.
* **Secrets Management:** Mandatory (including PostgreSQL and Redis passwords).
* **Resource Allocation:** Monitor and adjust limits, especially for `postgres`, `tarpit_api`, `escalation_engine`.
* **PostgreSQL:** Use a managed PostgreSQL service or ensure robust deployment/backup/HA for the self-hosted instance. Monitor performance.
* **Markov Corpus:** Provide a large, high-quality corpus for effective tarpit text generation. Retrain periodically if needed.
* **Hop Limit Tuning:** Adjust `TAR_PIT_MAX_HOPS` based on observed traffic and server resources.
* **`REAL_BACKEND_HOST`:** Ensure this is correctly configured for your deployment topology.
* **Monitoring & Logging:** Implement external monitoring and log aggregation.
* **API Usage:** Manage third-party API usage (IP reputation, etc.).
* **CAPTCHA:** Requires separate implementation in your main application.
* **Firewall:** Configure appropriately.
* **Backups:** Back up PostgreSQL data, Redis data, models, configs, secrets, certs.
* **Updates:** Keep components updated.