import logging
import os
import subprocess  # nosec B404
from typing import Optional

from ..waf_manager import NGINX_RELOAD_CMD, reload_waf_rules
from . import config
from .config import ALLOWED_RULES_DOMAINS, CRS_DOWNLOAD_URL, MODSEC_DIR, RULES_URL
from .crs import download_and_extract_crs, rollback_crs
from .download import (
    RulesDownloadError,
    check_source,
    download_bounded,
    validate_rules_text,
    verify_digest,
)
from .kubernetes import KUBE_AVAILABLE, get_kubernetes_api, update_configmap

logger = logging.getLogger(__name__)


# --- Core Functions ---
def fetch_rules(
    url: str,
    allowed_domains: Optional[list[str]] = None,
    expected_sha256: Optional[str] = None,
) -> str:
    """Download rules content from the given URL, or return "" and log why it was refused.

    The source must be HTTPS on a public address (and on an allowed host when ``RULES_ALLOWED_DOMAINS`` is set), the
    body is size-limited, checked against ``RULES_SHA256`` when configured, and rejected if it is not valid ModSecurity
    text or uses a directive that runs code or reads other files (#1907).

    Args:
        url: The HTTPS URL to fetch.
        allowed_domains: Optional list of allowed hostnames.
        expected_sha256: Optional pinned digest of the download; defaults to ``RULES_SHA256``.
    """
    if not url:
        logger.error("No URL provided to fetch rules.")
        return ""

    domains = allowed_domains if allowed_domains is not None else ALLOWED_RULES_DOMAINS
    digest = config.RULES_SHA256 if expected_sha256 is None else expected_sha256
    try:
        check_source(url, domains)
        body = download_bounded(url, timeout=15, max_bytes=config.RULES_MAX_BYTES)
        verify_digest(body, digest, require=config.RULES_REQUIRE_DIGEST, what="Rules download")
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RulesDownloadError("rules are not valid UTF-8") from exc
        problems = validate_rules_text(text)
        if problems:
            raise RulesDownloadError("rules rejected: " + "; ".join(problems[:3]))
    except RulesDownloadError as exc:
        logger.error("Rules from %s not used: %s", url, exc)
        return ""
    logger.info("Successfully fetched rules file.")
    return text


def _reload_after_crs() -> bool:
    """Reload Nginx after a CRS install; if it will not load the new rules, restore the previous ones."""
    try:
        subprocess.run(NGINX_RELOAD_CMD, check=True)  # nosec B603
        return True
    except (subprocess.CalledProcessError, OSError) as exc:
        logger.error("Failed to reload Nginx after CRS install: %s", exc)
        if rollback_crs(MODSEC_DIR):
            try:
                subprocess.run(NGINX_RELOAD_CMD, check=True)  # nosec B603
            except (subprocess.CalledProcessError, OSError) as retry_exc:
                logger.error("Nginx would not reload the previous rules either: %s", retry_exc)
        return False


def _install_crs() -> bool:
    logger.info("Fetching OWASP CRS from %s", CRS_DOWNLOAD_URL)
    return download_and_extract_crs(CRS_DOWNLOAD_URL, MODSEC_DIR) and _reload_after_crs()


def _install_rules_url() -> bool:
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
        logger.info("Not in Kubernetes or library unavailable. Updating local rules file.")
        reload_waf_rules(rules_content.splitlines())
    return True


def _run_as_script() -> bool:
    """Helper to execute the module's main block."""
    logger.info("WAF rules fetcher script started.")
    if not (_install_crs() if CRS_DOWNLOAD_URL else _install_rules_url()):
        return False
    logger.info("WAF rules fetcher script finished.")
    return True
