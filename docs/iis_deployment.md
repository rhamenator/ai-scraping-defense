# Deploying with IIS on Windows

This guide describes how to run the AI Scraping Defense stack on a Windows server using **Internet Information Services (IIS)** instead of Nginx.

## Prerequisites

- Windows Server with IIS installed.
- [Application Request Routing](https://learn.microsoft.com/iis/extensions/planning-for-arr/) and [URL Rewrite](https://learn.microsoft.com/iis/extensions/url-rewrite-module/) modules enabled.
- Python installed and able to create virtual environments.
- Redis and PostgreSQL running locally or accessible on the network.

## 1. Start the Python Services

Use PowerShell to create a virtual environment and install the project dependencies:

```powershell
# From the repository root
./reset_venv.ps1
```

Start each service in its own terminal. Example for the AI Service:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn src.ai_service.ai_webhook:app --host 127.0.0.1 --port 8000
```

Repeat for the other services, matching the ports defined in `docker-compose.yaml`.

## 2. Configure IIS as a Reverse Proxy

1. Open **IIS Manager** and choose your server in the **Connections** pane.
2. Double-click **Application Request Routing Cache** and select **Server Proxy Settings**.
3. Check **Enable proxy** and apply the change.
4. Under your site, open **URL Rewrite** and add rules that forward traffic to the running Python services.

Example rule for the Admin UI:

| Setting       | Value                                  |
|---------------|----------------------------------------|
| Pattern       | `admin/(.*)`                           |
| Rewrite URL   | `http://localhost:5002/{R:1}`          |

Add similar rules for the other services. A catch‑all rule can forward the rest of the traffic to your main backend on port 8080.

## 3. Recreating Lua Logic

The Nginx deployment uses Lua scripts for bot detection. With IIS you have two options:

1. **Custom HttpModule** – Write a .NET module to inspect requests, query Redis for blocklisted IPs, and forward suspicious requests to the AI service.
2. **Gateway Service** – Route all traffic to a small Python service that performs the same checks before proxying to the backend.

## 4. Managing Secrets

Generate required secrets with the PowerShell script:

```powershell
./Generate-Secrets.ps1
```

Ensure the resulting environment variables are available to each service when you launch them.

---

Replacing Nginx with IIS requires more manual configuration but allows the stack to run on a pure Windows environment. Once IIS routes are defined and the Python services are running, the system behaves the same as the Docker-based setup.
