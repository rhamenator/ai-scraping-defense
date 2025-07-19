# AI Scraping Defense

This project provides a multi-layered, microservice-based defense system against sophisticated AI-powered web scrapers and malicious bots.

## Key Features

- **Layered Defense:** Uses a combination of Nginx, Lua, and a suite of Python microservices for defense in depth.
- **Intelligent Analysis:** Employs heuristics, a machine learning model, and optional LLM integration to analyze suspicious traffic.
- **Model Agnostic:** A flexible adapter pattern allows for easy integration with various ML models and LLM providers (OpenAI, Mistral, Cohere, etc.).
- **Active Countermeasures:** Includes a "Tarpit API" to actively waste the resources of confirmed bots.
- **End-User Verification:** Optional reCAPTCHA challenge service logs successful verifications for training data.
- **Rate Limiting:** Adaptive per-IP limits updated by a small daemon writing to Nginx.
- **Community Blocklist:** Optional daemon to sync IPs from a shared blocklist service.
- **Public Community Blocklist Service:** Lightweight FastAPI app for contributors to share and fetch malicious IPs.
- **Federated Threat Sharing:** Peer-to-peer sync exchanges blocklisted IPs between deployments.
- **Containerized:** Fully containerized with Docker and ready for deployment on Kubernetes.
- **Multi-Tenant Ready:** Namespace configuration and Redis keys with `TENANT_ID` for easy isolation.
- **Optional Cloud Integrations:** Toggle CDN caching, DDoS mitigation, managed TLS, and a Web Application Firewall using environment variables.
- **Plugin API:** Drop-in Python modules allow custom rules to extend detection logic.
- **Anomaly Detection via AI:** Move beyond heuristics and integrate anomaly detection models for more adaptive security.
- **Automated Configuration Recommendations:** AI-driven service that analyzes traffic patterns and suggests firewall and tarpit tuning.

## Getting Started (Local Development)

This setup uses Docker Compose to orchestrate all the necessary services on your local machine.

### Prerequisites

- Docker and Docker Compose
- Python 3.10+
- A shell environment (Bash for Linux/macOS, PowerShell for Windows)

### Setup Instructions
For a one-command setup, run `./quickstart_dev.sh` on Linux/macOS or `quickstart_dev.ps1` on Windows.



1. **Clone the Repository:**

    ```bash
    git clone [https://github.com/your-username/ai-scraping-defense.git](https://github.com/your-username/ai-scraping-defense.git)
    cd ai-scraping-defense
    ```

2. **Create Environment File:**
    Copy the example environment file to create your local configuration.

    ```bash
    cp sample.env .env
    ```

    Open the `.env` file and review the default settings. You do not need to change anything to get started, but this is where you would add your API keys later.
    Set `TENANT_ID` to a unique value for each isolated deployment.
    To enable the CAPTCHA verification service, populate `CAPTCHA_SECRET` with your reCAPTCHA secret key.
    Tarpit behavior can be tuned with `TARPIT_MAX_HOPS` and `TARPIT_HOP_WINDOW_SECONDS` to automatically block clients that spend too much time in the tarpit.

3. **Set Up Python Virtual Environment:**
    Run the setup script to create a virtual environment and install all Python dependencies.

    *On Linux or macOS:*

    ```bash
    sudo bash ./reset_venv.sh
    ```

    *On Windows (in a PowerShell terminal as Administrator):*

    ```powershell
    .\reset_venv.ps1
    ```

4. **Generate Secrets:**
    Run the secret generation script to create passwords for the database, Admin UI, and other services. It writes a `kubernetes/secrets.yaml` file and prints the credentials to your console. The script **does not** modify `.env` unless you use the optional `--update-env` flag.

    *On Linux or macOS:*

    ```bash
    # prints credentials only
    bash ./generate_secrets.sh

    # optionally update .env with the generated values
    bash ./generate_secrets.sh --update-env
    ```

    *On Windows (in a PowerShell terminal):*

    ```powershell
    .\Generate-Secrets.ps1
    ```
    These scripts generate a `.htpasswd` entry using bcrypt with cost factor 12 for securing access to the Admin UI.

    **Important:** The script will print the generated credentials to the console. Copy these and save them in a secure password manager.

5. **Enable HTTPS (Optional):**
    Edit the `.env` file to set `ENABLE_HTTPS=true` and provide paths to your TLS certificate and key.

    ```bash
    ENABLE_HTTPS=true
    TLS_CERT_PATH=./nginx/certs/tls.crt
    TLS_KEY_PATH=./nginx/certs/tls.key
    ```

    Make sure the certificate files exist at those paths or update them accordingly.

6. **Launch the Stack:**
    Build and start all the services using Docker Compose.

    ```bash
    docker-compose up --build -d
    ```

    If you'd like to try the proxy in front of a WordPress site, run `./setup_wordpress_website.sh` (or `./setup_wordpress_website.ps1` on Windows) instead. It launches WordPress and MariaDB containers on the same Docker network and sets `REAL_BACKEND_HOST` automatically.

7. **Access the Services:**
    - **Admin UI:** `http://localhost:5002`
    - **Cloud Dashboard:** `http://localhost:5006`
    - **Your Application (via proxy):** `http://localhost:8080`
    - **HTTPS (if enabled):** `https://localhost:8443`

## Project Structure

- `src/`: Contains all Python source code for the microservices.
- `kubernetes/`: Contains all Kubernetes manifests for production deployment.
- `nginx/`: Nginx and Lua configuration files.
- `docs/`: Project documentation, including architecture and data flows.
- `test/`: Unit tests for the Python services.
- `sample.env`: Template for local development configuration.
- `Dockerfile`: A single Dockerfile used to build the base image for all Python services.
- `jszip-rs/`: Rust implementation of the fake JavaScript archive generator.
- `markov-train-rs/`: Rust implementation of the Markov training utility.

## Markov Training Utility (Rust)

`markov-train-rs` contains a high-performance implementation of the corpus loader.
It exposes a `train_from_corpus_rs` function callable from Python via PyO3.

Build the extension with Cargo:

```bash
cd markov-train-rs
cargo build --release
```

Once built, call the function to populate PostgreSQL:

```bash
python -c "import markov_train_rs, os; markov_train_rs.train_from_corpus_rs(os.environ['CORPUS_FILE_PATH'])"
```

Ensure the usual `PG_HOST`, `PG_PORT`, `PG_DBNAME`, `PG_USER`, and `PG_PASSWORD_FILE` environment variables are set so the library can connect to PostgreSQL.

## JS ZIP Generator (Rust)

`jszip-rs` provides an optional Rust backend for generating the large fake JavaScript archives used by the tarpit. It can be built with Cargo:

```bash
cd jszip-rs
cargo build --release
```
The build requires Python development headers (e.g. `python3-dev` on Debian-based systems) so that PyO3 can link against `libpython`.

The resulting `jszip_rs` Python module will be used automatically if available.

## Training the Detection Model

The `src/rag/training.py` script now accepts a `--model` flag to select which
machine learning algorithm to train. Supported values are `rf` (RandomForest,
default), `xgb` (XGBoost), and `lr` (Logistic Regression). Example usage:

```bash
python src/rag/training.py --model xgb
```

This flexibility makes it easy to experiment with different classifiers.

## Automated Deployment

Use `./quick_deploy.sh` (Linux/macOS) or `quick_deploy.ps1` (Windows) for a streamlined Kubernetes deployment. These scripts generate required secrets and apply all manifests using kubectl.

## Load Testing Helpers

To experiment with the stack's performance under load, run the helper script:

```bash
./setup_load_test_suite.sh (or ./setup_load_test_suite.ps1 on Windows)
```

It installs common open-source tools such as **wrk**, **siege**, **ab**, **k6**, and **locust**. Use them responsibly and only against environments you control.

After installing the tools, you can run a basic stress test using the provided scripts:

```powershell
./stress_test.ps1 -Target http://your-linux-host:8080 -VUs 50 -DurationSeconds 30
```

```bash
./stress_test.sh http://your-linux-host:8080
```
