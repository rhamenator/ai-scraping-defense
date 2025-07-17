import os
import logging

ENABLE_WAF = os.getenv("ENABLE_WAF", "false").lower() == "true"
WAF_RULES_PATH = os.getenv("WAF_RULES_PATH", "/etc/nginx/waf_rules.conf")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_waf_rules() -> list[str]:
    """Load WAF rules from disk if enabled."""
    if not ENABLE_WAF:
        logger.debug("WAF disabled.")
        return []
    try:
        with open(WAF_RULES_PATH, 'r') as f:
            rules = [line.strip() for line in f if line.strip()]
        logger.info(f"Loaded {len(rules)} WAF rules.")
        return rules
    except FileNotFoundError:
        logger.error(f"WAF rules file not found: {WAF_RULES_PATH}")
        return []
