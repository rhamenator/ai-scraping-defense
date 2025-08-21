import logging
import os
import subprocess
from typing import Optional
from urllib.parse import urlparse

import requests

from ..waf_manager import NGINX_RELOAD_CMD, reload_waf_rules
from .config import ALLOWED_RULES_DOMAINS, CRS_DOWNLOAD_URL, MODSEC_DIR, RULES_URL
from .crs import download_and_extract_crs
from .kubernetes import KUBE_AVAILABLE, get_kubernetes_api, update_configmap

logger = logging.getLogger(__name__)


# --- Core Functions ---
def fetch_rules(url: str, allowed_domains: Optional[list[str]] = None) -> str:
    """Download rules content from the given URL.

    Args:
        url: The HTTPS URL to fetch.
        allowed_domains: Optional list of allowed hostnames.
    """
    if not url:
        logger.error("No URL provided to fetch rules.")
        return ""

    if not url.startswith("https://"):
        logger.error("Rules URL must start with 'https://': %s", url)
        return ""

    domains = allowed_domains if allowed_domains is not None else ALLOWED_RULES_DOMAINS
    if domains:
        hostname = urlparse(url).hostname
        if hostname not in domains:
            logger.error("Rules URL host %s not in allowlist.", hostname)
            return ""

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        logger.info("Successfully fetched rules file.")
        return response.text
    except requests.exceptions.RequestException as exc:
        logger.error("Failed to fetch rules from %s: %s", url, exc)
        return ""


def _run_as_script() -> None:
    """Helper to execute the module's main block."""
    logger.info("WAF rules fetcher script started.")

    if CRS_DOWNLOAD_URL:
        logger.info("Fetching OWASP CRS from %s", CRS_DOWNLOAD_URL)
        success = download_and_extract_crs(CRS_DOWNLOAD_URL, MODSEC_DIR)
        if success:
            subprocess.run(NGINX_RELOAD_CMD, check=False)
    else:
        rules_content = fetch_rules(RULES_URL)

        if not rules_content:
            logger.warning("No rules content retrieved. Exiting.")
            return

        if KUBE_AVAILABLE and os.environ.get("KUBERNETES_SERVICE_HOST"):
            logger.info("Running inside Kubernetes. Attempting to update ConfigMap.")
            kube_api = get_kubernetes_api()
            if kube_api:
                update_configmap(kube_api, rules_content)
        else:
            logger.info(
                "Not in Kubernetes or library unavailable. Updating local rules file."
            )
            reload_waf_rules(rules_content.splitlines())

    logger.info("WAF rules fetcher script finished.")
