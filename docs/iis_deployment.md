# Deploying with IIS on Windows

This guide describes how to run the AI Scraping Defense stack on a Windows server using **Internet Information Services (IIS)** instead of Nginx.

## Prerequisites

- Windows Server with IIS installed.
- [Application Request Routing](https://learn.microsoft.com/iis/extensions/planning-for-arr/) and [URL Rewrite](https://learn.microsoft.com/iis/extensions/url-rewrite-module/) modules enabled.
- Python installed and able to create virtual environments.
- Redis and PostgreSQL running locally or accessible on the network.

## 1. Start the Python Services

Run the helper script to launch all required services:

```powershell
./iis/start_services.ps1
```

This script resets the virtual environment (unless `-NoReset` is supplied) and
starts the AI Service, Escalation Engine, Tarpit API, and Admin UI in separate
PowerShell windows. Ports are read from environment variables or fall back to the
defaults in `sample.env`.

## 2. Configure IIS as a Reverse Proxy

You can script this setup with `iis/configure_proxy.ps1` or perform the steps manually:

1. Open **IIS Manager** and choose your server in the **Connections** pane.
2. Double-click **Application Request Routing Cache** and select **Server Proxy Settings**.
3. Check **Enable proxy** and apply the change.
4. Under your site, open **URL Rewrite** and add rules that forward traffic to the running Python services. The script will create rules for the Admin UI and a catch‑all backend route automatically.

To automate these settings, run:

```powershell
./iis/configure_proxy.ps1
```

## 3. Recreating Lua Logic

The Nginx deployment uses Lua scripts for bot detection. With IIS you have two options:

1. **Custom HttpModule** – Compile the sample module in `iis/DefenseModule` and register it with your site. The module checks the Redis blocklist and can escalate suspicious requests to the AI service.
2. **Gateway Service** – Launch `src/iis_gateway/main.py` to run a lightweight proxy that applies similar checks in Python before forwarding to the real backend.

To build the HttpModule open a Developer Command Prompt for Visual Studio and run:

```cmd
msbuild iis\DefenseModule\DefenseModule.csproj /p:Configuration=Release
```

Copy the resulting DLL to your IIS modules folder and add it under **Modules** in IIS Manager.

To start the gateway service:

```powershell
.\.venv\Scripts\Activate.ps1
python -m src.iis_gateway.main
```

Set the `BACKEND_URL` environment variable to the address of your application.
The gateway also supports per-IP rate limiting and header validation. Set
`RATE_LIMIT_PER_MINUTE` to a positive value to enable basic throttling.

## 4. Managing Secrets

Generate required secrets with the PowerShell script:

```powershell
./Generate-Secrets.ps1
```

Ensure the resulting environment variables are available to each service when you launch them.

---

Replacing Nginx with IIS requires more manual configuration but allows the stack to run on a pure Windows environment. Once IIS routes are defined and the Python services are running, the system behaves the same as the Docker-based setup.
