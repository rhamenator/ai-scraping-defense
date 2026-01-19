import logging
import os
import subprocess  # nosec B404
from typing import Optional

import requests

from src.shared.ssrf_protection import SSRFProtectionError, validate_url

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

    domains = allowed_domains if allowed_domains is not None else ALLOWED_RULES_DOMAINS

    # Use centralized SSRF protection
    try:
        validate_url(
            url,
            allowed_domains=domains if domains else None,
            require_https=True,
            block_private_ips=True,
        )
    except SSRFProtectionError as e:
        logger.error("SSRF protection blocked rules fetch from %s: %s", url, e)
        return ""

    try:
        response = requests.get(url, timeout=15, allow_redirects=False)
        response.raise_for_status()
        logger.info("Successfully fetched rules file.")
        return response.text
    except requests.exceptions.RequestException as exc:
        logger.error("Failed to fetch rules from %s: %s", url, exc)
        return ""


def _run_as_script() -> bool:
    """Helper to execute the module's main block."""
    logger.info("WAF rules fetcher script started.")

    if CRS_DOWNLOAD_URL:
        logger.info("Fetching OWASP CRS from %s", CRS_DOWNLOAD_URL)
        success = download_and_extract_crs(CRS_DOWNLOAD_URL, MODSEC_DIR)
        if not success:
            return False
        try:
            subprocess.run(NGINX_RELOAD_CMD, check=True)  # nosec B603
        except subprocess.CalledProcessError as exc:
            logger.error("Failed to reload Nginx after CRS install: %s", exc)
            return False
    else:
        rules_content = fetch_rules(RULES_URL)

        if not rules_content:
            logger.warning("No rules content retrieved. Exiting.")
            return False

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
    return True
