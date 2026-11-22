import os

RULES_URL = os.getenv("RULES_DOWNLOAD_URL", "")
ALLOWED_RULES_DOMAINS = [
    d.strip() for d in os.getenv("RULES_ALLOWED_DOMAINS", "").split(",") if d.strip()
]
CRS_DOWNLOAD_URL = os.getenv("CRS_DOWNLOAD_URL", "")
CONFIGMAP_NAME = os.getenv("WAF_RULES_CONFIGMAP_NAME", "waf-rules")
CONFIGMAP_NAMESPACE = os.getenv("KUBERNETES_NAMESPACE", "default")
RULES_FILE_NAME = os.getenv("RULES_FILE_NAME", "custom.rules")
WAF_RULES_PATH = os.getenv(
    "WAF_RULES_PATH", f"/etc/nginx/modsecurity/rules/{RULES_FILE_NAME}"
)
MODSEC_DIR = os.getenv("MODSECURITY_DIR", "/etc/nginx/modsecurity")


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, "") or default)
    except ValueError:
        return default
    return value if value > 0 else default


# Integrity and bounds for downloaded rules (#1907). A digest pins the exact bytes an operator reviewed; without one the
# download is accepted but a warning is logged, unless RULES_REQUIRE_DIGEST is true, which refuses unpinned downloads.
RULES_SHA256 = os.getenv("RULES_SHA256", "").strip().lower()
CRS_SHA256 = os.getenv("CRS_SHA256", "").strip().lower()
RULES_REQUIRE_DIGEST = os.getenv("RULES_REQUIRE_DIGEST", "false").lower() == "true"
RULES_MAX_BYTES = _int_env("RULES_MAX_BYTES", 5 * 1024 * 1024)
CRS_MAX_DOWNLOAD_BYTES = _int_env("CRS_MAX_DOWNLOAD_BYTES", 25 * 1024 * 1024)
CRS_MAX_EXTRACTED_BYTES = _int_env("CRS_MAX_EXTRACTED_BYTES", 100 * 1024 * 1024)
CRS_MAX_FILE_BYTES = _int_env("CRS_MAX_FILE_BYTES", 20 * 1024 * 1024)
CRS_MAX_MEMBERS = _int_env("CRS_MAX_MEMBERS", 5000)
CRS_MAX_EXPANSION_RATIO = _int_env("CRS_MAX_EXPANSION_RATIO", 100)

# How the running Nginx is told about new rules after the CRS is installed (#1907):
#   local       run `nginx -s reload` in this container (default; right when this process runs beside Nginx)
#   kubernetes  roll the Deployment named WAF_RESTART_DEPLOYMENT so its pods start with the new rules (CronJob use)
#   none        install only; Nginx picks the rules up whenever it next restarts or reloads
WAF_RELOAD_MODE = os.getenv("WAF_RELOAD_MODE", "local").strip().lower()
WAF_RESTART_DEPLOYMENT = os.getenv("WAF_RESTART_DEPLOYMENT", "nginx-proxy")
