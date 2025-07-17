# AI Scraping Defense

This project provides a multi-layered, microservice-based defense system against sophisticated AI-powered web scrapers and malicious bots.

## Key Features

- **Layered Defense:** Uses a combination of Nginx, Lua, and a suite of Python microservices for defense in depth.
- **Intelligent Analysis:** Employs heuristics, a machine learning model, and optional LLM integration to analyze suspicious traffic.
- **Model Agnostic:** A flexible adapter pattern allows for easy integration with various ML models and LLM providers (OpenAI, Mistral, Cohere, etc.).
- **Active Countermeasures:** Includes a "Tarpit API" to actively waste the resources of confirmed bots.
- **Containerized:** Fully containerized with Docker and ready for deployment on Kubernetes.

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
