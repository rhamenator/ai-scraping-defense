# Configuration Reference

This page documents all environment variables consumed by the Python services. Defaults come from `src/shared/config.py` unless noted.

## HashiCorp Vault Configuration

The system supports HashiCorp Vault for enhanced secret management with multiple authentication methods and automatic rotation.

| Variable | Default | Description |
| --- | --- | --- |
| `VAULT_ADDR` | *(none)* | Vault server address (e.g., `http://vault:8200`) |
| `VAULT_TOKEN` | *(none)* | Vault authentication token |
| `VAULT_NAMESPACE` | *(none)* | Vault namespace (for Enterprise) |
| `VAULT_ROLE_ID` | *(none)* | AppRole role ID for authentication |
| `VAULT_SECRET_ID` | *(none)* | AppRole secret ID for authentication |
| `VAULT_KUBERNETES_ROLE` | *(none)* | Kubernetes role for authentication in K8s |
| `VAULT_KUBERNETES_JWT_PATH` | `/var/run/secrets/kubernetes.io/serviceaccount/token` | Path to Kubernetes service account JWT |
| `VAULT_MOUNT_POINT` | `secret` | KV v2 secrets engine mount point |
| `VAULT_VERIFY_TLS` | `true` | Verify TLS certificates for Vault connections |
| `VAULT_TIMEOUT` | `30` | Timeout in seconds for Vault operations |

### Vault Secret Path Format

Secrets can reference Vault paths using the `_VAULT_PATH` suffix:

```bash
# Instead of setting REDIS_PASSWORD_FILE, use:
REDIS_PASSWORD_FILE_VAULT_PATH=secret/data/ai-defense/database/redis

# The system will:
# 1. Try to read from Vault using vault_client
# 2. Fall back to file-based secrets if Vault is unavailable
# 3. Extract the 'value' key from the secret data
```

### Authentication Methods

The Vault client tries authentication methods in this order:

1. **Token Authentication** - Uses `VAULT_TOKEN`
2. **AppRole Authentication** - Uses `VAULT_ROLE_ID` and `VAULT_SECRET_ID`
3. **Kubernetes Authentication** - Uses `VAULT_KUBERNETES_ROLE` and JWT from service account

### Secret Rotation

The system includes automated secret rotation capabilities:

- **Rotation Policies**: Define per-secret rotation schedules (e.g., 90 days)
- **Pre/Post Hooks**: Execute custom logic before/after rotation
- **Version Management**: Automatic cleanup of old secret versions
- **Compliance Monitoring**: Track secret age and compliance status
- **Prometheus Metrics**: Monitor secret operations and health

See `src/security/secret_rotation.py` for rotation service implementation.

## Service Hosts

| Variable | Default | Service |
| --- | --- | --- |
| `AI_SERVICE_HOST` | `ai_service` | AI Service Webhook |
| `ESCALATION_ENGINE_HOST` | `escalation_engine` | Escalation Engine |
| `TARPIT_API_HOST` | `tarpit_api` | Tarpit API |
| `ADMIN_UI_HOST` | `admin_ui` | Admin UI |
| `CLOUD_DASHBOARD_HOST` | `cloud_dashboard` | Cloud Dashboard |
| `CONFIG_RECOMMENDER_HOST` | `config_recommender` | Config Recommender |
| `PROMPT_ROUTER_HOST` | `prompt_router` | Prompt Router |

## Service Ports

| Variable | Default | Service |
| --- | --- | --- |
| `AI_SERVICE_PORT` | `8000` | AI Service Webhook |
| `ESCALATION_ENGINE_PORT` | `8003` | Escalation Engine |
| `TARPIT_API_PORT` | `8001` | Tarpit API |
| `ADMIN_UI_PORT` | `5002` | Admin UI |
| `CLOUD_DASHBOARD_PORT` | `5006` | Cloud Dashboard |
| `CONFIG_RECOMMENDER_PORT` | `8010` | Config Recommender |
| `PROMPT_ROUTER_PORT` | `8009` | Prompt Router |

## Admin UI Authentication

| Variable | Default | Description |
| --- | --- | --- |
| `ADMIN_UI_USERNAME` | `admin` | Basic auth username |
| `ADMIN_UI_PASSWORD_HASH` | *(none)* | bcrypt hash for admin password |
| `ADMIN_UI_2FA_SECRET` | *(none)* | TOTP secret for MFA |
| `WEBAUTHN_RP_ID` | `localhost` | WebAuthn relying party ID |
| `WEBAUTHN_ORIGIN` | `http://localhost` | WebAuthn origin |
| `WEBAUTHN_TOKEN_TTL` | `300` | WebAuthn token TTL in seconds |
| `PASSKEY_TOKEN_TTL` | `300` | Passkey token TTL in seconds |
| `WEBAUTHN_AUTHENTICATOR_ATTACHMENT` | `none` | `none`, `platform`, or `cross-platform` |

## Redis Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `REDIS_HOST` | `redis` | Hostname for Redis |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_DB_BLOCKLIST` | `2` | DB index for blocklist data |
| `REDIS_DB_TAR_PIT_HOPS` | `4` | DB index for tarpit hop counts |
| `REDIS_DB_FREQUENCY` | `3` | DB index for request frequency |
| `REDIS_DB_FINGERPRINTS` | `5` | DB index for browser fingerprints |
| `REDIS_PASSWORD_FILE` | *(none)* | Path to file containing Redis password |

## General Settings

| Variable | Default | Description |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Python log verbosity |
| `APP_ENV` | `production` | Deployment environment name |
| `DEBUG` | `false` | Enable debug mode in services |
| `TENANT_ID` | `default` | Namespace prefix for multi-tenant setups |

## Tarpit and Blocklist

| Variable | Default | Description |
| --- | --- | --- |
| `ESCALATION_ENDPOINT` | `http://escalation_engine:8003/escalate` | URL used by Nginx Lua to send escalation data |
| `TAR_PIT_MIN_DELAY_SEC` | `0.6` | Minimum tarpit delay |
| `TAR_PIT_MAX_DELAY_SEC` | `1.2` | Maximum tarpit delay |
| `SYSTEM_SEED` | `default_system_seed_value_change_me` | Seed for tarpit text generation; **must be overridden** |
| `TAR_PIT_MAX_HOPS` | `250` | Max recorded tarpit hops |
| `TAR_PIT_HOP_WINDOW_SECONDS` | `86400` | Sliding window for hop counts |
| `BLOCKLIST_TTL_SECONDS` | `86400` | How long IPs remain blocked |
| `ENABLE_TARPIT_CATCH_ALL` | `true` | Send unmatched requests to the tarpit |

> **Note:** `SYSTEM_SEED` must be set to a unique value. The Tarpit API raises an error if the default placeholder is used.

## Security Middleware

These settings apply to services created via `src.shared.middleware.create_app()`.

| Variable | Default | Description |
| --- | --- | --- |
| `ENABLE_HTTPS` | `false` | Redirect HTTP requests to HTTPS and enable HSTS |
| `RATE_LIMIT_REQUESTS` | `100` | Requests allowed per client IP per window |
| `RATE_LIMIT_WINDOW` | `60` | Rate limit window size in seconds |
| `MAX_BODY_SIZE` | `1048576` | Max request body size in bytes |
| `SECURITY_HTTPS_REDIRECT_CANONICAL_HOST` | *(none)* | Optional canonical `host[:port]` for HTTPS redirects |
| `SECURITY_HTTPS_REDIRECT_ALLOWED_HOSTS` | *(none)* | Optional comma-separated list of allowed `host[:port]` values for HTTPS redirects |
| `SECURITY_MAX_PATH_LENGTH` | `2048` | Max URL path length in bytes (0 disables the check) |
| `SECURITY_MAX_QUERY_STRING_LENGTH` | `4096` | Max query string length in bytes (0 disables the check) |
| `SECURITY_MAX_HEADER_COUNT` | `100` | Max number of request headers (0 disables the check) |
| `SECURITY_MAX_HEADER_VALUE_LENGTH` | `8192` | Max single header value length in bytes (0 disables the check) |

## Alerts and Webhooks

| Variable | Default | Description |
| --- | --- | --- |
| `ALERT_METHOD` | `none` | How the AI Service sends notifications |
| `ALERT_GENERIC_WEBHOOK_URL` | *(none)* | Generic webhook target |
| `ALERT_GENERIC_WEBHOOK_URL_FILE` | *(none)* | File containing generic webhook target |
| `ALERT_SLACK_WEBHOOK_URL` | *(none)* | Slack webhook target |
| `ALERT_SLACK_WEBHOOK_URL_FILE` | *(none)* | File containing Slack webhook target |
| `ALERT_SMTP_HOST` | `mailhog` | SMTP server hostname |
| `ALERT_SMTP_PORT` | `587` | SMTP server port |
| `ALERT_SMTP_USER` | *(none)* | SMTP username |
| `ALERT_SMTP_PASSWORD_FILE` | `/run/secrets/smtp_password` | File containing SMTP password |
| `ALERT_SMTP_USE_TLS` | `true` | Use TLS for SMTP |
| `ALERT_EMAIL_FROM` | `$ALERT_SMTP_USER` | Sender address for alerts |
| `ALERT_EMAIL_TO` | *(none)* | Destination email addresses |
| `ALERT_MIN_REASON_SEVERITY` | `Local LLM` | Minimum reason to trigger alerts |
| `ENABLE_COMMUNITY_REPORTING` | `true` | Report IPs to community blocklist |
| `COMMUNITY_BLOCKLIST_REPORT_URL` | *(none)* | URL to send community reports |
| `COMMUNITY_BLOCKLIST_API_KEY_FILE` | `/run/secrets/community_blocklist_api_key` | API key file for community reports |
| `COMMUNITY_BLOCKLIST_REPORT_TIMEOUT` | `10.0` | HTTP timeout for reporting |
| `WEBHOOK_SHARED_SECRET` | *(none)* | Secret used to verify webhook HMAC signatures |
| `WEBHOOK_RATE_LIMIT_REQUESTS` | `60` | Requests allowed per IP in each window |
| `WEBHOOK_RATE_LIMIT_WINDOW` | `60` | Rate limit window size in seconds |

## Escalation Engine and Classification

| Variable | Default | Description |
| --- | --- | --- |
| `ESCALATION_THRESHOLD` | `0.8` | Score needed to block a request |
| `ESCALATION_API_KEY` | *(none)* | Key required for Escalation Engine API |
| `ESCALATION_WEBHOOK_URL` | *(none)* | HTTPS endpoint for escalations; must start with `https://` |
| `ESCALATION_WEBHOOK_ALLOWED_DOMAINS` | *(none)* | Comma-separated list of approved webhook domains |
| `LOCAL_LLM_API_URL` | *(none)* | URL of local LLM API |
| `LOCAL_LLM_MODEL` | *(none)* | Model name for local LLM API |
| `LOCAL_LLM_TIMEOUT` | `45.0` | Timeout in seconds for local LLM |
| `EXTERNAL_CLASSIFICATION_API_URL` | *(none)* | External classification API |
| `EXTERNAL_API_KEY` | *(secret file)* | API key for external service |
| `EXTERNAL_API_TIMEOUT` | `15.0` | Timeout in seconds for external API |
| `ENABLE_LOCAL_LLM_CLASSIFICATION` | `true` | Use local LLM for scoring |
| `ENABLE_EXTERNAL_API_CLASSIFICATION` | `true` | Use external API for scoring |
| `ENABLE_IP_REPUTATION` | `false` | Query IP reputation service |
| `IP_REPUTATION_API_URL` | *(none)* | IP reputation endpoint |
| `IP_REPUTATION_API_KEY_FILE` | `/run/secrets/ip_reputation_api_key` | IP reputation API key file |
| `IP_REPUTATION_TIMEOUT` | `10.0` | Timeout for reputation lookup |
| `IP_REPUTATION_MALICIOUS_SCORE_BONUS` | `0.3` | Score bonus for malicious IPs |
| `IP_REPUTATION_MIN_MALICIOUS_THRESHOLD` | `50` | Minimum reputation score considered malicious |

## CAPTCHA

| Variable | Default | Description |
| --- | --- | --- |
| `ENABLE_CAPTCHA_TRIGGER` | `false` | Require CAPTCHA for low-scoring requests |
| `CAPTCHA_SCORE_THRESHOLD_LOW` | `0.2` | Score at which CAPTCHA is triggered |
| `CAPTCHA_SCORE_THRESHOLD_HIGH` | `0.5` | Score at which CAPTCHA failure blocks |
| `CAPTCHA_VERIFICATION_URL` | *(none)* | CAPTCHA verification endpoint |
| `CAPTCHA_SECRET_FILE` | *(none)* | Secret key file for verification |
| `CAPTCHA_SUCCESS_LOG` | `/app/logs/captcha_success.log` | Log path for successful verifications |
| `TRAINING_ROBOTS_TXT_PATH` | `/app/config/robots.txt` | robots.txt used for training |

## Model and Anomaly Detection

| Variable | Default | Description |
| --- | --- | --- |
| `MODEL_TYPE` | *(none)* | Adapter type for the primary model |
| `MODEL_VERSION` | *(none)* | Version string reported to metrics |
| `ANOMALY_MODEL_PATH` | *(none)* | Path to optional anomaly detection model |
| `ANOMALY_THRESHOLD` | `0.7` | Threshold for anomaly detector |
| `ENABLE_TARPIT_LLM_GENERATOR` | `false` | Use an LLM to generate tarpit pages |
| `TARPIT_LLM_MODEL_URI` | *(none)* | Model URI for tarpit generator |
| `TARPIT_LLM_MAX_TOKENS` | `400` | Max tokens for tarpit LLM |
| `ENABLE_AI_LABYRINTH` | `true` | Enable endless labyrinth pages |
| `TARPIT_LABYRINTH_DEPTH` | `5` | Depth for AI labyrinth |
| `ENABLE_FINGERPRINTING` | `true` | Track browser fingerprints |

## Tracking Windows

| Variable | Default | Description |
| --- | --- | --- |
| `FREQUENCY_WINDOW_SECONDS` | `300` | Period for request frequency tracking |
| `FINGERPRINT_WINDOW_SECONDS` | `604800` | TTL for stored fingerprints |
| `FINGERPRINT_REUSE_THRESHOLD` | `3` | Allowed fingerprint reuse count |

## File Paths

| Variable | Default | Service |
| --- | --- | --- |
| `AUDIT_LOG_FILE` | `/app/logs/audit.log` | Shared audit logger; file is created with owner-only (600) permissions |
| `HONEYPOT_LOG_FILE` | `/app/logs/honeypot_hits.log` | Honeypot logger |
| `CAPTCHA_SUCCESS_LOG` | `/app/logs/captcha_success.log` | CAPTCHA services |
| `BLOCK_LOG_FILE` | `/app/logs/block_events.log` | Admin UI |
| `DECISIONS_DB_PATH` | `/app/data/decisions.db` | Decision DB |

## Runtime

| Variable | Default | Description |
| --- | --- | --- |
| `UVICORN_WORKERS` | `2` | Worker processes for FastAPI services |

This list focuses on the variables loaded via `src/shared/config.py` and the modules that build on that configuration. Other scripts such as the optional blocklist sync daemons define additional variables. Refer to `sample.env` for a full listing.
