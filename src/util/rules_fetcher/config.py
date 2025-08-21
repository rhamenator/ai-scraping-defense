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
