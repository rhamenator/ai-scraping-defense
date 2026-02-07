# **AI Scraping Defense: From Local Test to Production**

This guide provides a complete path for deploying the AI Scraping Defense system, starting with a test setup on your personal computer and finishing with a production-ready deployment on a live web server.

### **Introduction: The Two-Step Process**

1. **Local Testing (Your Computer):** First, you'll run the system locally to get familiar with how it works, connect it to a test website, and see its features in a safe environment.
2. **Production Deployment (Live Server):** Once you're comfortable, you'll move to a live server. This involves pointing to a domain name, handling real web traffic on standard ports (80 for HTTP, 443 for HTTPS), and enabling encryption.

### **Part 1: Local Testing Environment**

This part is for running the system on your personal computer for evaluation.

#### **Prerequisites**

Before you begin, you need to install a couple of free tools:

1. **Git:** A tool for downloading the project's code. [Download here](https://git-scm.com/downloads).
2. **Docker Desktop:** The application that runs the system's components. [Download here](https://www.docker.com/products/docker-desktop/). Make sure it's running before you start.

#### **Initial Setup**

Follow these steps in your **Terminal (Mac/Linux)** or **PowerShell (Windows)**.

1. Download or Update the Code:
   Run the following command to download the project files:
   ```
   git clone https://github.com/rhamenator/ai-scraping-defense.git
   ```

   **Note:** If you see an error that the folder ai-scraping-defense already exists, it just means you've downloaded it before. In that case, run these two commands instead to make sure you have the latest version:
   ```
   cd ai-scraping-defense
   git pull
   ```

2. Navigate into the Project Directory:
   If you just ran the git clone command, you now need to move into the directory it created:
   ```
   cd ai-scraping-defense
   ```

   *(If you ran git pull above, you can skip this step as you are already in the correct directory.)*
3. **Run the Quick Deploy Script:** This is the easiest way to start the system locally. It will use test ports like 8080 to avoid conflicting with other services on your computer.
   * **Mac/Linux:** ```./scripts/linux/quick_deploy.sh```
   * **Windows:** ```./scripts/windows/quick_deploy.ps1```

At this point, you can connect the system to a local or test website. The key thing to remember is that this local setup uses http://localhost:8080 for the website and http://localhost:8081 for the admin panel.

### **Part 2: Production Deployment**

This section covers deploying the system to a live server to protect a real website.

#### **Production Prerequisites**

* **A Server:** You need a server with a public IP address (e.g., a Virtual Private Server from a cloud provider like DigitalOcean, Linode, AWS, etc.).
* **A Domain Name:** You need a domain name (e.g., your-cool-site.com) and the ability to edit its DNS records.

#### **Step 1: Point Your Domain to the Server**

In your domain registrar's DNS settings, create an **'A' record** that points your domain (e.g., your-cool-site.com) to your server's public IP address.

#### **Step 2: Server Setup**

Log into your server's terminal and perform the initial setup.

1. **Install Git and Docker Engine (If Not Already Installed):** Your server will need Git and the Docker Engine. Most modern server images come with Git. You can check if they are installed by running ```git --version``` and ```docker --version```. If you get an error, you'll need to install them. You can find instructions for installing the Docker Engine here: [Install Docker Engine](https://docs.docker.com/engine/install/).
2. Download or Update the Code:
   Run the following command to download the project files:

   ```
   git clone https://github.com/rhamenator/ai-scraping-defense.git
   ```

   **Note:** If you see an error that the folder ai-scraping-defense already exists, run these two commands instead to get the latest version:

   ```
   cd ai-scraping-defense
   git pull
   ```

3. Navigate into the Project Directory:
   If you just ran git clone, move into the new directory:

   ```
   cd ai-scraping-defense
   ```

   *(If you ran git pull, you are already in the correct directory.)*
4. **Create the Configuration File:**

   ```
   cp sample.env .env
   ```

#### **Step 3: Configure for Production**

This is the most important step. You need to edit two files: .env and docker-compose.yaml.

1. **Edit the .env file:** Open it with a text editor (nano .env).
   * **UPSTREAM_HOST and UPSTREAM_PORT**: Set these to the address of the actual website you want to protect. If your website is running in another Docker container on the same server, the host will be the name of that container (e.g., my-website-container) and the port will be whatever it exposes (e.g., 80).
   * **DOMAIN_NAME**: Set this to your actual domain name (e.g., your-cool-site.com). This is required for obtaining an SSL certificate.
   * **CERTBOT_EMAIL**: Provide your email address. This is used by Let's Encrypt to notify you about your certificate.
   * **Set Strong Secrets:** Change all the default passwords and secrets in this file to secure, randomly generated values.
2. Edit the docker-compose.yaml file:
   We need to change the ports for the NGINX service so it listens on the standard web ports.
   * Find the nginx service definition.
   * Change the ports section from 8080:80 to listen on ports 80 and 443.

**Change this:**  ports:
    - "8080:80"
    - "8081:81"
**To this:**  ports:
    - "80:80"
    - "443:443"
    - "8081:81" # Keep this for the admin panel, but consider securing it.

#### **Step 4: Launch and Secure the System**

1. **Run the Deployment Script:** This project includes a script that builds the containers and requests the SSL certificate for you.
   * **On your server's terminal:**

     ```
     ./deploy.sh
     ```

2. **Verify It's Working:**
   * Open a web browser and navigate to https://your-cool-site.com. You should see your website, now secured with an "https://" connection.
   * You can access the admin panel at http://<your_server_ip>:8081. For production, you should lock this down to be accessible only from your IP address.

#### **Production Architecture Diagram**

This diagram shows how traffic flows in the live production environment.

``` mermaid
graph TD
    A[User on the Internet] -->|Request to https://your-cool-site.com| B(Firewall/Cloud Provider);
    B -->|Ports 80/443| C[NGINX Reverse Proxy];
    C -->|Analyzes Request| D{AI Service};
    D -->|Is the request safe?| C;
    C -->|Forwards safe traffic| E[Your Live Website];
    D -->|Blocks or Tarpits malicious traffic| F[Action Taken];
```

### **How to Stop the Application**

Run this command from the project directory on your server:

```
docker-compose down
```
