# AI Scraping Defense


[![codecov](https://codecov.io/gh/rhamenator/ai-scraping-defense/branch/main/graph/badge.svg)](https://codecov.io/gh/rhamenator/ai-scraping-defense)

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
- **Anomaly Detection via AI:** Move beyond heuristics and integrate anomaly detection models for more adaptive security. ✅
- **Automated Configuration Recommendations:** AI-driven service that analyzes traffic patterns and suggests firewall and tarpit tuning.

## Architecture Overview

The following diagram provides a high-level view of how the major components interact. See [docs/architecture.md](docs/architecture.md) for a deeper explanation.

```mermaid
graph TD
    subgraph "User / Bot Traffic"
        direction LR
        User["👤 User"]
        Bot["🤖 Bot"]
    end

    subgraph "Defense System"
        direction TB
        Nginx["🛡️ Nginx Proxy w/ Lua"]

        subgraph "Analysis & Logic (Python Microservices)"
            direction LR
            AIService["AI Service Webhook"]
            EscalationEngine["🧠 Escalation Engine"]
            AdminUI["📊 Admin UI"]
            CloudDashboard["☁️ Cloud Dashboard"]
            ConfigRecommender["🔧 Config Recommender"]
            BlocklistSync["🔄 Blocklist Sync"]
            PeerSync["🔄 Peer Sync"]
            RateLimitDaemon["⚙️ Rate Limit Daemon"]
        end

        subgraph "Countermeasures"
            TarpitAPI["🕸️ Tarpit API"]
        end

        subgraph "Data & State Stores"
            direction LR
            Redis["⚡ Redis\n(Blocklist, Cache)"]
            Postgres["🐘 PostgreSQL\n(Markov Data)"]
        end
    end

    subgraph "External Services"
        LLM["☁️ LLM APIs\n(OpenAI, Mistral, etc.)"]
        CommunityBlocklist["☁️ Community Blocklist"]
        PeerDeployments["☁️ Peer Deployments"]
    end

    User -- "Legitimate Request" --> Nginx
    Bot -- "Suspicious Request" --> Nginx

    Nginx -- "Block Immediately" --> Bot
    Nginx -- "Forward for Analysis" --> AIService
    Nginx -- "Serve Content" --> User
    Nginx -- "Redirect to Tarpit" --> Bot

    AIService -- "Queues Request" --> EscalationEngine
    EscalationEngine -- "Reads/Writes" --> Redis
    EscalationEngine -- "Reads" --> Postgres
    EscalationEngine -- "Calls for Final Verdict" --> LLM
    EscalationEngine -- "Updates" --> AdminUI
    AdminUI -- "Streams Metrics" --> CloudDashboard
    AdminUI -- "Feeds" --> ConfigRecommender
    ConfigRecommender -- "Suggestions" --> AdminUI
    BlocklistSync -- "Update" --> Redis
    PeerSync -- "Share IPs" --> Redis
    RateLimitDaemon -- "Adjust Limits" --> Nginx
    BlocklistSync -- "Fetch IPs" --> CommunityBlocklist
    PeerSync -- "Exchange IPs" --> PeerDeployments

    AdminUI -- "Manages" --> Redis

    TarpitAPI -- "Reads" --> Postgres
```

## Quick Local Setup

Run the automated script after cloning the repository:

```bash
git clone https://github.com/your-username/ai-scraping-defense.git
cd ai-scraping-defense

sudo ./quickstart_dev.sh   # use sudo on Linux/macOS; run quickstart_dev.ps1 on Windows
```

On Windows, open an **Administrator PowerShell** window and run `quickstart_dev.ps1` instead.

The script copies `sample.env`, generates secrets, installs Python requirements using

`pip install -r requirements.txt -c constraints.txt`, and launches Docker Compose for you.
The stack requires Rust 1.78.0. `mise` (or `rustup`) installs this toolchain automatically.
If you see a warning about `idiomatic_version_file_enable_tools`, silence it with:

```bash
mise settings add idiomatic_version_file_enable_tools rust
```

You can ignore the message if Rust 1.78.0 is already installed.


For a step-by-step explanation of each setup script, see [docs/getting_started.md](docs/getting_started.md).

## Manual Local Setup

Follow these steps if you prefer to configure everything yourself.

1. **Clone the Repository:**

    ```bash
    git clone https://github.com/your-username/ai-scraping-defense.git
    cd ai-scraping-defense
    ```

2. **Create Environment File:**
    Copy the example environment file or use the interactive helper to customise settings.

    ```bash
    cp sample.env .env
    # optional guided setup
    python scripts/interactive_setup.py
    ```

    The interactive helper can also launch Docker Compose or deploy to
    Kubernetes when it finishes, if you choose to proceed automatically.
    If you agree when prompted, your secrets are saved in a local SQLite
    database at `secrets/local_secrets.db`. Delete this file or answer **n**
    during the prompt to disable the database and clear stored values.

    Open `.env` and review the defaults. Set `TENANT_ID` for isolated deployments and add any API keys you plan to use. For **production** deployments update `NGINX_HTTP_PORT` to `80` and `NGINX_HTTPS_PORT` to `443`. `REAL_BACKEND_HOST` controls where allowed traffic is forwarded when the proxy sits in front of another site.

3. **Set Up Python Virtual Environment:**
    Run the setup script to create a virtual environment and install all Python dependencies.
    After the environment is created, install the project requirements with pinned
    constraints:

    ```bash
    pip install -r requirements.txt -c constraints.txt
    ```

    *On Linux or macOS:*

    ```bash
    sudo bash ./reset_venv.sh
    ```

    *On Windows (PowerShell as Administrator):*

    ```powershell
    .\reset_venv.ps1
    ```

4. **Generate Secrets:**
    Run the secret generation script to create passwords for the database, Admin UI, and other services. It writes a `kubernetes/secrets.yaml` file and prints the credentials to your console. If you used `interactive_setup.py` above, this step has already been performed.

    *On Linux or macOS:*

    ```bash
    bash ./generate_secrets.sh
    # export credentials to a JSON file
    bash ./generate_secrets.sh --export-path my_secrets.json
    ```

    *On Windows:*

    ```powershell
    .\Generate-Secrets.ps1
    # save credentials to a JSON file
    .\Generate-Secrets.ps1 -ExportPath my_secrets.json
    ```

5. **Enable HTTPS (Optional):**
    Edit `.env` and set `ENABLE_HTTPS=true` with paths to your certificate and key.

    ```bash
    ENABLE_HTTPS=true
    TLS_CERT_PATH=./nginx/certs/tls.crt
    TLS_KEY_PATH=./nginx/certs/tls.key
    ```

6. **Launch the Stack:**
    Build and start the services with Docker Compose.

    ```bash
    docker-compose up --build -d
    ```

    If you'd like to try the proxy in front of a WordPress site, run `./setup_wordpress_website.sh` (or `./setup_wordpress_website.ps1` on Windows) instead. It launches WordPress and MariaDB containers and sets `REAL_BACKEND_HOST` automatically. For a smaller test, `./setup_fake_website.sh` creates a simple nginx site and updates the variable in the same way.

7. **Access the Services:**
    - **Admin UI:** `http://localhost:5002`
    - **Cloud Dashboard:** `http://localhost:5006`
    - **Your Application:** `http://localhost:8080`
    - **HTTPS (if enabled):** `https://localhost:8443`

## Optional Features

Several integrations are disabled by default to keep the stack lightweight. You can enable them by editing `.env`:

- **Web Application Firewall** (`ENABLE_WAF`) – Mounts ModSecurity rules from `WAF_RULES_PATH` for additional filtering.
- **Global CDN** (`ENABLE_GLOBAL_CDN`) – Connects to your CDN provider using `CLOUD_CDN_API_TOKEN` for edge caching.
- **DDoS Mitigation** (`ENABLE_DDOS_PROTECTION`) – Reports malicious traffic to an external service configured by `DDOS_PROTECTION_API_KEY`.
- **Managed TLS** (`ENABLE_MANAGED_TLS`) – Automatically issues certificates via `TLS_PROVIDER` with contact email `TLS_EMAIL`.
- **CAPTCHA Verification** – Populate `CAPTCHA_SECRET` to activate reCAPTCHA challenges.
- **Fail2ban** – Start the `fail2ban` container to insert firewall rules based on blocked IPs. See [docs/fail2ban.md](docs/fail2ban.md) for details.
- **LLM Tarpit Pages** (`ENABLE_TARPIT_LLM_GENERATOR`) – Use an LLM to generate fake pages when a model URI is provided.

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
## Configuring AI Models

The detection services load a model specified by the `MODEL_URI` value in `.env`. Examples include a local scikit-learn file or an external API:

```bash
MODEL_URI=sklearn:///app/models/bot_detection_rf_model.joblib
MODEL_URI=openai://gpt-4-turbo
MODEL_URI=mistral://mistral-large-latest
```

For remote providers, set the corresponding API key in `.env` (`OPENAI_API_KEY`, `MISTRAL_API_KEY`, etc.).

## Model Adapter Guide

The [Model Adapter Guide](docs/model_adapter_guide.md) explains all available schemes and how to extend the system with new providers.

## Markov Training Utility (Rust)

`markov-train-rs` contains a high-performance implementation of the corpus loader.
It exposes a `train_from_corpus_rs` function callable from Python via PyO3.
The repository is pinned to **Rust 1.78.0** via `rust-toolchain.toml`. Ensure
that toolchain is installed before building the Rust crates.

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

## Quick Kubernetes Deployment

Run the helper script to deploy everything to Kubernetes in one step. Ensure the
`kubernetes/secrets.yaml` file already exists (generate it with
`generate_secrets.sh` or the interactive setup):

```bash
./quick_deploy.sh       # or .\quick_deploy.ps1 on Windows
```

If you're on Windows, run `quick_deploy.ps1` from an **Administrator PowerShell** window.

The script applies all manifests using `kubectl`; it does not generate secrets.

## Manual Kubernetes Deployment

For a detailed, step-by-step guide see [docs/kubernetes_deployment.md](docs/kubernetes_deployment.md). The `deploy.sh` and `deploy.ps1` scripts provide a manual approach if you need more control.

## Cloud Deployment (GKE Example)

To deploy the stack to a managed Kubernetes service such as Google Kubernetes Engine, follow the instructions in [docs/cloud_provider_deployment.md](docs/cloud_provider_deployment.md). Convenience scripts are provided for automation:

```bash
./gke_deploy.sh       # or .\gke_deploy.ps1 on Windows
```


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
