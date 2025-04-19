# **Getting Started with the AI Scraping Defense Stack**

This guide provides the steps needed to set up, configure, run, and perform basic tests on the AI Scraping Defense Stack using Docker Compose.

## **1\. Prerequisites**

Ensure you have the following installed on your system:

* **Docker:** The containerization platform. ([Install Docker](https://docs.docker.com/engine/install/))  
* **Docker Compose:** Tool for defining and running multi-container Docker applications (usually included with Docker Desktop, otherwise install separately: [Install Docker Compose](https://docs.docker.com/compose/install/))  
* **Git:** For cloning the repository. ([Install Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git))  
* **(Optional) redis-cli:** Useful for verifying the blocklist directly in Redis.  
* **(Optional) curl:** Useful for sending test HTTP requests.

## **2\. Setup & Configuration**

1. **Clone the Repository:**  
   git clone <https://github.com/rhamenator/ai-scraping-defense.git>
   cd ai-scraping-defense

2. Create Configuration Directories:  
   Ensure the following directories exist in the project root (some might be created by Docker later, but good to have placeholders):  
   mkdir \-p config data logs models archives secrets shared

3. Create robots.txt:  
   Place your website's robots.txt file inside the config/ directory:  
   ./config/robots.txt

   The training script (rag/training.py) and potentially other components rely on this path.  
4. **Create .env File:**  
   * Find the sample.env file (we created this conceptually \- ensure it's physically present or copy the content from our chat).  
   * Copy it to a new file named .env in the project root:  
     cp sample.env .env

   * **Edit .env:** Open the .env file in a text editor.  
     * **Review Defaults:** Check default values for REDIS\_\*, LOCAL\_LLM\_\*, etc.  
     * **Configure Alerting (Optional):** If you want to test alerting, set ALERT\_METHOD to slack, smtp, or webhook and fill in the corresponding ALERT\_\* variables (e.g., ALERT\_SLACK\_WEBHOOK\_URL). For initial testing, leaving ALERT\_METHOD=none is fine.  
     * **Configure External APIs (Optional):** If testing external classification, set EXTERNAL\_API\_URL and EXTERNAL\_API\_KEY.  
     * **Configure Local LLM (Optional):** If testing local LLM classification, ensure LOCAL\_LLM\_API\_URL points to your running LLM server (e.g., Ollama) and LOCAL\_LLM\_MODEL matches a model available on that server.  
     * **Secrets:** For sensitive values like ALERT\_SMTP\_PASSWORD or EXTERNAL\_API\_KEY, consider using Docker Secrets (see step below). For initial testing, you *can* put them in .env, but **ensure .env is listed in your .gitignore**.  
5. **Set up Docker Secrets (Optional but Recommended for Production):**  
   * If using secrets for sensitive data (like ALERT\_SMTP\_PASSWORD):  
     * Create a directory (e.g., ./secrets). **Add this directory to .gitignore**.  
     * Create files within ./secrets containing *only* the secret value, e.g., ./secrets/smtp\_password.txt.  
     * Ensure the secrets: block at the end of docker-compose.yml correctly references these host files.  
     * Ensure the relevant service (e.g., ai\_service) has the secret mounted in docker-compose.yml and the application code reads from the file path specified by the environment variable (e.g., ALERT\_SMTP\_PASSWORD\_FILE).

## **3\. Data Setup (Optional \- Needed for Training)**

If the tester needs to run the model training script (rag/training.py):

1. **Place Apache Log File:** Copy a sample (or full) Apache access log file (Combined Log Format) into the data/ directory and ensure its name matches the LOG\_FILE\_PATH in training.py (default: /app/data/apache\_access.log inside the container, corresponding to ./data/apache\_access.log on the host).  
2. **Create Placeholder Feedback Logs:** Create empty placeholder files for the feedback mechanism if the actual logs aren't available yet but you want training.py to run without file-not-found errors:  
   touch ./logs/honeypot\_hits.log  
   touch ./logs/captcha\_success.log

   *(Note: The training script will load empty sets from these files, so labeling quality will depend entirely on heuristics until real feedback data is generated).*

## **4\. Build and Run the Stack**

1. **Build Docker Images:**  
   docker-compose build

   *(This might take some time on the first run)*  
2. **Start Services:**  
   docker-compose up \-d

   *(The \-d runs containers in detached mode)*  
3. **Check Container Status:**  
   docker-compose ps

   *(Ensure all services listed in docker-compose.yml are Up or Running)*  
4. **View Logs (Optional):**  
   docker-compose logs \-f \# View logs from all services  
   docker-compose logs \-f nginx \# View logs for a specific service  
   docker-compose logs \-f escalation\_engine  
   docker-compose logs \-f ai\_service

   *(Look for connection errors (e.g., Redis, LLM API) or startup issues)*

## **5\. Basic Testing & Verification**

1. **Access Admin UI:** Open <http://localhost/admin/> (or <http://localhost:5002> if NGINX proxy isn't working) in your browser. You should see the dashboard, potentially with metrics starting at 0\.  
2. **Test Tarpit Trigger (Bad UA):**  
   * From your terminal, send a request with a known bad User-Agent:  
     curl \-A "TestPythonBot/1.0" <http://localhost/some-random-page> \-v

   * **Expected:** You should receive a 302 Redirect response pointing to /api/tarpit. NGINX logs (docker-compose logs nginx) might show the redirect. The Tarpit API logs (docker-compose logs tarpit\_api) should show a "TAR PIT HIT" message. The Escalation Engine (docker-compose logs escalation\_engine) should show "Received escalation request".  
3. **Test Escalation & Blocklisting:**  
   * Triggering the tarpit (as above) should cause the Escalation Engine to analyze the request. If the combined score is high enough (or other triggers met), it should call the AI Service webhook (/analyze).  
   * Check AI Service logs (docker-compose logs ai\_service). Look for "Webhook Received" and "Action taken: ip\_blocklisted".  
   * Check Redis: If redis-cli is installed, connect and check the blocklist set (DB 2 by default):  
     redis-cli \-n 2 SISMEMBER blocklist:ip \<IP\_ADDRESS\_OF\_CURL\_MACHINE\>

     *(Replace \<IP\_ADDRESS\_OF\_CURL\_MACHINE\> with the IP seen in the logs, likely your host machine's Docker bridge IP or 172.x.x.x. The command should return (integer) 1 if blocked).*  
4. **Test Blocklist Enforcement:**  
   * Immediately after confirming the IP is blocklisted in Redis, repeat the curl command from step 2\.  
   * **Expected:** You should now receive a 403 Forbidden response directly from NGINX. Check NGINX logs for messages from check\_blocklist.lua indicating the block.  
5. **Test Alerting (If Configured):**  
   * If you configured ALERT\_METHOD and the necessary credentials/URLs in .env, check the target system (Slack channel, email inbox, generic webhook receiver) for an alert message after triggering the blocklist in step 3\. Check ai\_service logs for success/error messages related to sending alerts.

## **6\. Running Training (Optional)**

1. Ensure prerequisite data (Apache logs, robots.txt, optionally feedback logs) is in place (see Section 3).  
2. Execute the training script inside a relevant container (one with Python, required libraries, and volume mounts for data/models/config). The escalation\_engine service definition is a good candidate if its build includes all dependencies from the root requirements.txt.  
   docker-compose run \--rm escalation\_engine python rag/training.py

   *(Note: Use run \--rm to start a one-off container for the script and remove it afterwards. Adjust service name if needed)*  
3. **Expected Output:** The script will print progress messages for log parsing, labeling, feature extraction, model training/evaluation, and saving the model (.joblib) and fine-tuning data (.jsonl) to the respective volume mounts (./models, ./data/finetuning\_data).

## **7\. Stopping the Stack**

docker-compose down

*(This stops and removes the containers, network, but preserves named volumes like redis\_data)*

docker-compose down \-v \# Add \-v to also remove named volumes

This guide should provide a solid starting point for testing the core functionality of the system. Remember to adapt paths and configurations based on the specific testing environment.
