# **Getting Started (Local Development)**

This guide will walk you through setting up the AI Scraping Defense project for local development. The entire stack is orchestrated using Docker Compose, which makes the setup process straightforward.

## **Prerequisites**

* **Docker & Docker Compose:** Ensure they are installed and running on your system.  
* **Python:** Version 3.10 or higher.  
* **Git:** For cloning the repository.  
* **A Shell Environment:** Bash (for Linux/macOS) or PowerShell (for Windows).

## **Step-by-Step Setup**
If you prefer an automated setup, simply run `./quickstart_dev.sh` on Linux/macOS or `quickstart_dev.ps1` on Windows.


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
```

``` PowerShell
# On Windows (in a PowerShell terminal)
Copy-Item sample.env .env
```

Now, open the .env file in your code editor. For now, you can leave the default values as they are. This is where you would add your real API keys for services like OpenAI or Mistral when you're ready to use them.

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

The application requires several secrets to run (e.g., database passwords). A script is provided to generate these securely. It creates `kubernetes/secrets.yaml` and prints the credentials to your console. By default it **does not** modify your `.env` file.

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

### **6.1. Accessing the Admin UI**

To access the Admin UI, navigate to [http://localhost:5002](http://localhost:5002) in your web browser. The dashboard now visualizes key metrics like the number of bots detected and how many IPs are currently blocked. It still shows the environment-based configuration and lets you manage the blocklist. A couple of runtime-only options (such as log level and escalation endpoint) can be adjusted on this page, but any changes will be lost when the service restarts.

### **6.2. Accessing the MailHog Interface**

MailHog is used to capture emails sent by the application for testing purposes. You can access it at [http://localhost:8025](http://localhost:8025). This is useful for verifying email functionality without sending real emails.

### **6.3. Adding Custom Rule Plugins**

You can extend the detection heuristics by placing Python modules inside the `plugins/` directory. Set `ENABLE_PLUGINS=true` in your `.env` file and restart the stack. Each module should define a `check(metadata)` function returning a numeric adjustment.

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
