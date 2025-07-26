# **Getting Started (Local Development)**

This guide will walk you through setting up the AI Scraping Defense project for local development. The entire stack is orchestrated using Docker Compose, which makes the setup process straightforward. For a broad overview of the project, see the [README](../README.md).

## **Quick Local Setup**

Run the helper script after cloning the repository:

```bash
git clone https://github.com/your-username/ai-scraping-defense.git
cd ai-scraping-defense
./quickstart_dev.sh       # automatically uses .ps1 on Windows
```

The helper scripts detect your platform and call the PowerShell variants
whenever the setup runs on Windows.

The script copies `sample.env`, generates secrets, installs dependencies, and launches Docker Compose.

## **Prerequisites**

* **Docker & Docker Compose:** Ensure they are installed and running on your system.
* **Python:** Version 3.10 or higher.
* **Git:** For cloning the repository.
* **A Shell Environment:** Bash (for Linux/macOS) or PowerShell (for Windows).

## **Manual Local Setup**


### **1. Clone the Repository**

First, clone the project from GitHub to your local machine.

``` bash
git clone [https://github.com/your-username/ai-scraping-defense.git](https://github.com/your-username/ai-scraping-defense.git)  
cd ai-scraping-defense
```

### **2. Create Your Environment File**

The project uses a .env file to manage all local configuration, including secrets and port mappings. We provide a template to get you started.

Copy the template to create your own local .env file:

``` bash
# On Linux or macOS
cp sample.env .env
# optional guided setup
python [scripts/interactive_setup.py](../scripts/interactive_setup.py)
```

``` PowerShell
# On Windows (in a PowerShell terminal)
Copy-Item sample.env .env
python [scripts/interactive_setup.py](../scripts/interactive_setup.py)
```

Now, open the .env file in your code editor. For now, you can leave the default values as they are. This is where you would add your real API keys for services like OpenAI or Mistral when you're ready to use them. For **production** deployments, update `NGINX_HTTP_PORT` to `80` and `NGINX_HTTPS_PORT` to `443` so the proxy listens on the standard web ports.

#### **Minimal Required Variables**

To bring the stack up, only a handful of settings must be reviewed in `.env`:

- `MODEL_URI` &mdash; choose the detection model. Examples include:
  - `sklearn:///app/models/bot_detection_rf_model.joblib`
  - `openai://gpt-4-turbo`
  - `mistral://mistral-large-latest`
- The API key matching your chosen provider: `OPENAI_API_KEY`, `MISTRAL_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, or `COHERE_API_KEY`.
- `EXTERNAL_API_KEY` for optional integrations.
- Port values such as `NGINX_HTTP_PORT`, `NGINX_HTTPS_PORT`, and `ADMIN_UI_PORT` typically work as-is.

The `[scripts/interactive_setup.py](../scripts/interactive_setup.py)` helper referenced above will prompt for these values and update `.env` automatically.

### **3. Set Up the Python Virtual Environment**

To keep your project's Python dependencies isolated, we use a virtual environment. A setup script is provided to automate this process.

* **On Linux or macOS:**  
  **You may need to run this with sudo to install system dependencies**

```bash
sudo bash ./reset_venv.sh
```

* **On Windows (in a PowerShell terminal as Administrator):**

``` PowerShell
.\reset_venv.ps1
```

This script will create a virtual environment in the .venv directory, install all required Python packages from requirements.txt, and ensure any necessary system libraries are present.

### **4. Generate Local Secrets**

The application requires several secrets to run (e.g., database passwords). A script is provided to generate these securely. It creates `kubernetes/secrets.yaml` and prints the credentials to your console. By default it **does not** modify your `.env` file. If you used the interactive setup script, this step is performed automatically.

* **On Linux or macOS:**

```  bash
  ./generate_secrets.sh
  # optionally update your .env automatically
  ./generate_secrets.sh --update-env
```

* **On Windows (in a PowerShell terminal):**

``` PowerShell
  .\Generate-Secrets.ps1
```

When run from the interactive helper, the correct script is chosen
automatically.

**IMPORTANT:** The script will print the generated passwords and keys to your console. Copy this output immediately and store it in a secure password manager.

### **5. Launch the Application Stack**

With the configuration and secrets in place, you can now build and start all the services with a single command:

``` bash
# On Linux or macOS
docker-compose up --build -d
```

``` PowerShell
# On Windows (in a PowerShell terminal)
docker-compose up --build -d
```

* --build: This tells Docker Compose to build the Python service image using the Dockerfile.  
* -d: This runs the containers in detached mode (in the background).

### **6. Accessing the Services**

Once the containers are running, you can access the key services in your web browser:

* **Admin UI:** [http://localhost:5002](http://localhost:5002)
* **Your Application (via Nginx Proxy):** [http://localhost:8080](http://localhost:8080)
* **MailHog (Email Catcher):** [http://localhost:8025](http://localhost:8025)
* **Redis (for blocklist management):** [http://localhost:6379](http://localhost:6379) (not directly accessible via a web interface, but can be managed using Redis CLI or GUI tools).
* **Blocklist Sync Daemon:** runs automatically to pull updates from the community blocklist service.
* **Peer Sync Daemon:** exchanges blocklisted IPs with configured peer deployments.
* **Config Recommender:** [http://localhost:8010](http://localhost:8010) provides automated tuning suggestions.

### **6.1. Accessing the Admin UI**

To access the Admin UI, navigate to [http://localhost:5002](http://localhost:5002) in your web browser. The dashboard now visualizes key metrics like the number of bots detected and how many IPs are currently blocked. It still shows the environment-based configuration and lets you manage the blocklist. A couple of runtime-only options (such as log level and escalation endpoint) can be adjusted on this page, but any changes will be lost when the service restarts.

### **6.2. Accessing the MailHog Interface**

MailHog is used to capture emails sent by the application for testing purposes. You can access it at [http://localhost:8025](http://localhost:8025). This is useful for verifying email functionality without sending real emails.

### **6.3. Adding Custom Rule Plugins**

You can extend the detection heuristics by placing Python modules inside the `plugins/` directory. Set `ENABLE_PLUGINS=true` in your `.env` file and restart the stack. Each module should define a `check(metadata)` function returning a numeric adjustment.

### **6.4. Running a WordPress Test Site**

If you want to see how the defense stack performs in front of a real CMS, a helper script is provided to launch a WordPress instance and wire it into the proxy.

```bash
./setup_wordpress_website.sh (or ./setup_wordpress_website.ps1 on Windows)
```

The script starts the Docker Compose stack (if it is not already running) and then launches WordPress and its MariaDB database on the same `defense_network`. Traffic allowed by the proxy will reach WordPress via `REAL_BACKEND_HOST`. Once started you can visit the site directly at [http://localhost:8082](http://localhost:8082) or through the defense stack at [http://localhost:8080](http://localhost:8080).

### **7. Stopping the Application**

To stop the application stack, you can run:

``` bash
# On Linux or macOS
docker-compose down
```

``` PowerShell
# On Windows (in a PowerShell terminal)
docker-compose down
```

This will stop and remove all the containers defined in your docker-compose.yml file.

### **8. Stress Testing the Stack**

For load and performance experiments, a helper script installs several open-source testing tools. Run it from the project root:

```bash
./setup_load_test_suite.sh (or ./setup_load_test_suite.ps1 on Windows)
```

The script installs utilities like **wrk**, **siege**, **ab**, **k6**, and **locust**. After installation, you can try commands such as:

```bash
wrk -t4 -c100 -d30s http://localhost:8080
siege -c50 -t1m http://localhost:8080
ab -n 1000 -c100 http://localhost:8080/
```

Use these programs only against systems you own or have explicit permission to test.


## **Configuring AI Models**

Detection components load a model from the path or provider defined by `MODEL_URI` in `.env`.

```bash
MODEL_URI=sklearn:///app/models/bot_detection_rf_model.joblib
MODEL_URI=openai://gpt-4-turbo
MODEL_URI=mistral://mistral-large-latest
```

When using an external provider, populate the matching API key variable (e.g., `OPENAI_API_KEY` or `MISTRAL_API_KEY`). See [api_references.md](api_references.md) for all supported schemes.

## **Optional Features**

The `.env` file also contains toggles for several optional integrations:

- **Web Application Firewall** (`ENABLE_WAF`) mounts ModSecurity rules specified by `WAF_RULES_PATH`.
- **Global CDN** (`ENABLE_GLOBAL_CDN`) connects to a provider using `CLOUD_CDN_API_TOKEN`.
- **DDoS Mitigation** (`ENABLE_DDOS_PROTECTION`) sends threat data to a third-party service via `DDOS_PROTECTION_API_KEY`.
- **Managed TLS** (`ENABLE_MANAGED_TLS`) automatically issues certificates using `TLS_PROVIDER` and `TLS_EMAIL`.
- **CAPTCHA Verification** activates when `CAPTCHA_SECRET` is supplied.
- **LLM-Generated Tarpit Pages** (`ENABLE_TARPIT_LLM_GENERATOR`) require a `TARPIT_LLM_MODEL_URI`.

## **Quick Kubernetes Deployment**

To deploy the stack to a Kubernetes cluster in one step run:

```bash
./quick_deploy.sh       # automatically uses .ps1 on Windows
```

Like the local setup script, this command detects Windows and calls the
PowerShell version when needed.

This script generates the required secrets and applies all manifests using `kubectl`.

## **Manual Kubernetes Deployment**

For a detailed walkthrough see [kubernetes_deployment.md](kubernetes_deployment.md). The `deploy.sh` and `deploy.ps1` scripts allow you to apply the manifests manually when you need more control over the process.
