import logging
import os
import shutil
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


def _stage_and_activate(rules: list[str]) -> bool:
    """Write the new rules beside the live file and swap them in. Returns True if a previous file was backed up.

    Raises before ``os.replace`` if anything fails, leaving the live file exactly as it was.
    """
    previous_path = WAF_RULES_PATH + ".previous"
    staged_path = WAF_RULES_PATH + ".new"
    with open(staged_path, "w") as f:
        f.write("\n".join(rules) + "\n")
    had_previous = os.path.exists(WAF_RULES_PATH)
    if had_previous:
        shutil.copy2(WAF_RULES_PATH, previous_path)
    os.replace(staged_path, WAF_RULES_PATH)
    return had_previous


def _restore_after_failed_reload(had_previous: bool) -> None:
    """The new file is live and Nginx would not load it: put the previous one back, or remove a first-ever file."""
    if not had_previous:
        try:
            os.remove(WAF_RULES_PATH)
        except OSError:
            pass
        return
    try:
        os.replace(WAF_RULES_PATH + ".previous", WAF_RULES_PATH)
        logger.warning("Restored the previous WAF rules file.")
        subprocess.run(NGINX_RELOAD_CMD, check=True)  # nosec B603
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Could not restore the previous WAF rules: %s", exc)


def reload_waf_rules(rules: list[str]) -> bool:
    """Replace the rules file atomically and reload Nginx; restore the previous file if the reload fails (#1907)."""
    if not ENABLE_WAF:
        logger.debug("WAF disabled. Skipping reload.")
        return False

    activated = False
    had_previous = False
    try:
        had_previous = _stage_and_activate(rules)
        activated = True
        logger.info("WAF rules written. Reloading Nginx...")
        subprocess.run(NGINX_RELOAD_CMD, check=True)  # nosec B603
        logger.info("Nginx reloaded with new WAF rules.")
        return True
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to reload WAF rules: %s", exc)
        try:
            os.remove(WAF_RULES_PATH + ".new")
        except OSError:
            pass
        if activated:  # a failure before the swap leaves the live file untouched, so there is nothing to undo
            _restore_after_failed_reload(had_previous)
        return False


def is_xml_request(content_type: Optional[str]) -> bool:
    """Check if a request contains XML content based on Content-Type header."""
    return validate_xml_content_type(content_type)


if __name__ == "__main__":  # pragma: no cover - manual execution
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
