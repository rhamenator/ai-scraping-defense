# AI Scraping Defense

This project provides a multi-layered, microservice-based defense system against sophisticated AI-powered web scrapers and malicious bots.

## Key Features

- **Layered Defense:** Uses a combination of Nginx, Lua, and a suite of Python microservices for defense in depth.
- **Intelligent Analysis:** Employs heuristics, a machine learning model, and optional LLM integration to analyze suspicious traffic.
- **Model Agnostic:** A flexible adapter pattern allows for easy integration with various ML models and LLM providers (OpenAI, Mistral, Cohere, etc.).
- **Active Countermeasures:** Includes a "Tarpit API" to actively waste the resources of confirmed bots.
- **End-User Verification:** Optional reCAPTCHA challenge service logs successful verifications for training data.
- **Rate Limiting:** Basic per-IP request limits via Nginx to slow abusive clients.
- **Community Blocklist:** Optional daemon to sync IPs from a shared blocklist service.
- **Containerized:** Fully containerized with Docker and ready for deployment on Kubernetes.
- **Optional Cloud Integrations:** Toggle CDN caching, DDoS mitigation, managed TLS, and a Web Application Firewall using environment variables.

## Getting Started (Local Development)

This setup uses Docker Compose to orchestrate all the necessary services on your local machine.

### Prerequisites

- Docker and Docker Compose
- Python 3.10+
- A shell environment (Bash for Linux/macOS, PowerShell for Windows)

### Setup Instructions

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
    To enable the CAPTCHA verification service, populate `CAPTCHA_SECRET` with your reCAPTCHA secret key.

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
    Run the secret generation script. This will create passwords for the database, admin UI, etc., and store them in the `.env` file for Docker Compose to use.

    *On Linux or macOS:*

    ```bash
    bash ./generate_secrets.sh
    ```

    *On Windows (in a PowerShell terminal):*

    ```powershell
    .\Generate-Secrets.ps1
    ```

    **Important:** The script will print the generated credentials to the console. Copy these and save them in a secure password manager.

5. **Launch the Stack:**
    Build and start all the services using Docker Compose.

    ```bash
    docker-compose up --build -d
    ```

6. **Access the Services:**
    - **Admin UI:** `http://localhost:5002`
    - **Your Application (via proxy):** `http://localhost:8080`

## Project Structure

- `src/`: Contains all Python source code for the microservices.
- `kubernetes/`: Contains all Kubernetes manifests for production deployment.
- `nginx/`: Nginx and Lua configuration files.
- `docs/`: Project documentation, including architecture and data flows.
- `test/`: Unit tests for the Python services.
- `sample.env`: Template for local development configuration.
- `docker-compose.yaml`: Orchestrates the services for local development.
- `Dockerfile`: A single Dockerfile used to build the base image for all Python services.
- `markov-train-rs/`: Rust utility for loading Markov training data into PostgreSQL.
- `jszip-rs/`: Rust implementation of the fake JavaScript archive generator.

## Markov Training Utility (Rust)

`markov-train-rs` is a small command-line application that reads a text corpus and populates the Markov chain tables in PostgreSQL. The program uses the same environment variables as the Python script (`PG_HOST`, `PG_PORT`, `PG_DBNAME`, `PG_USER`, and `PG_PASSWORD_FILE`).

### Building

```bash
cd markov-train-rs
cargo build --release
```

### Running

Provide the path to a corpus file:

```bash
./target/release/markov-train-rs path/to/corpus.txt
```

Ensure the database credentials are available through environment variables or a password file as described above.

## JS ZIP Generator (Rust)

`jszip-rs` provides an optional Rust backend for generating the large fake JavaScript archives used by the tarpit. It can be built with Cargo similar to `markov-train-rs`:

```bash
cd jszip-rs
cargo build --release
```
The build requires Python development headers (e.g. `python3-dev` on Debian-based systems) so that PyO3 can link against `libpython`.

The resulting `jszip_rs` Python module will be used automatically if available.
