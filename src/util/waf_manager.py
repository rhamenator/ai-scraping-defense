import logging
import os
import subprocess  # nosec B404
from typing import Optional

from .secure_xml_parser import validate_xml_content_type

ENABLE_WAF = os.getenv("ENABLE_WAF", "true").lower() == "true"
WAF_RULES_PATH = os.getenv(
    "WAF_RULES_PATH",
    "/etc/nginx/modsecurity/rules/custom.rules",
)
NGINX_RELOAD_CMD = ["nginx", "-s", "reload"]

logger = logging.getLogger(__name__)


def load_waf_rules() -> list[str]:
    """Load WAF rules from disk if enabled."""
    if not ENABLE_WAF:
        logger.debug("WAF disabled.")
        return []
    try:
        with open(WAF_RULES_PATH, "r") as f:
            rules = [line.strip() for line in f if line.strip()]
        logger.info(f"Loaded {len(rules)} WAF rules.")
        return rules
    except FileNotFoundError:
        logger.error(f"WAF rules file not found: {WAF_RULES_PATH}")
        return []


def reload_waf_rules(rules: list[str]) -> bool:
    """Rewrite the rules file and reload Nginx to apply changes."""
    if not ENABLE_WAF:
        logger.debug("WAF disabled. Skipping reload.")
        return False

    try:
        with open(WAF_RULES_PATH, "w") as f:
            f.write("\n".join(rules) + "\n")
        logger.info("WAF rules written. Reloading Nginx...")
        subprocess.run(NGINX_RELOAD_CMD, check=True)  # nosec B603
        logger.info("Nginx reloaded with new WAF rules.")
        return True
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to reload WAF rules: %s", exc)
        return False


def is_xml_request(content_type: Optional[str]) -> bool:
    """Check if a request contains XML content based on Content-Type header."""
    return validate_xml_content_type(content_type)


if __name__ == "__main__":  # pragma: no cover - manual execution
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
