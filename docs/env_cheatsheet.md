# Environment Variable Cheat Sheet

The following variables from `.env` are the minimum values to review or set manually before starting the stack. Most defaults work for local testing, but production deployments may require changes.

| Variable | Purpose |
| --- | --- |
| `MODEL_URI` | Selects the detection model adapter and model path. Example: `sklearn:///app/models/bot_detection_rf_model.joblib` |
| `OPENAI_API_KEY` / `MISTRAL_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / `COHERE_API_KEY` | API key for your chosen LLM provider |
| `EXTERNAL_API_KEY` | Optional key for additional integrations |
| `NGINX_HTTP_PORT` | HTTP port exposed by the proxy (80 in production) |
| `NGINX_HTTPS_PORT` | HTTPS port exposed by the proxy (443 in production) |
| `ADMIN_UI_PORT` | Port for the Admin UI dashboard |
| `PROMPT_ROUTER_HOST` | Hostname of the Prompt Router service |
| `PROMPT_ROUTER_PORT` | Port of the Prompt Router service |
| `PROMETHEUS_PORT` | Port for the Prometheus metrics service |
| `GRAFANA_PORT` | Port for the Grafana dashboard |
| `REAL_BACKEND_HOSTS` | Comma-separated list of backend servers; overrides `REAL_BACKEND_HOST` |
| `REAL_BACKEND_HOST` | Fallback single backend when `REAL_BACKEND_HOSTS` is empty |
| `ALERT_SMTP_PASSWORD_FILE` / `ALERT_SMTP_PASSWORD` | Credentials for sending alert emails |
| `WATCHTOWER_INTERVAL` | Interval (in seconds) for the Watchtower update checker |

For more detail see the "Minimal Required Variables" section of `docs/getting_started.md`.
