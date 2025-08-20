"""
This module provides functions to flag, check, and remove IP addresses
in a dedicated Redis database. It uses a centralized Redis connection
utility from the 'shared' module.
"""

import logging
import os

from src.shared.config import tenant_key
from src.shared.redis_client import get_redis_connection

# Configure logging for this module
logger = logging.getLogger(__name__)

# Define the specific Redis database number for flagged IPs.
REDIS_DB_FLAGGED_IPS = 3

# TTL for flagged IP entries (seconds). Defaults to 7 days.
FLAGGED_IP_TTL_SECONDS = int(os.getenv("FLAGGED_IP_TTL_SECONDS", 604800))

# Number of times an IP can be flagged before it becomes a repeat offender.
# Repeat offenders are stored without a TTL (permanent until manually removed).
REPEAT_OFFENDER_THRESHOLD = int(os.getenv("REPEAT_OFFENDER_THRESHOLD", 3))

# Internal counter key prefix for tracking how many times an IP was flagged.
FLAG_COUNT_PREFIX = tenant_key("ip_flag_count:")


def flag_suspicious_ip(ip_address: str, reason: str = "Suspicious activity"):
    """
    Flags an IP address by setting a key in Redis.
    Connects to the dedicated database for flagged IPs.
    (Formerly flag_ip)
    """
    r = get_redis_connection(db_number=REDIS_DB_FLAGGED_IPS)
    if not r:
        logger.error("Redis unavailable. Cannot flag IP.")
        return False

    try:
        count_key = f"{FLAG_COUNT_PREFIX}{ip_address}"
        # Increment how many times this IP has been flagged
        flag_count = r.incr(count_key)
        r.expire(count_key, FLAGGED_IP_TTL_SECONDS)

        flag_key = tenant_key(f"ip_flag:{ip_address}")
        if flag_count > REPEAT_OFFENDER_THRESHOLD:
            # Repeat offenders are stored without expiration
            r.set(flag_key, reason)
        else:
            r.setex(flag_key, FLAGGED_IP_TTL_SECONDS, reason)

        logger.info(
            f"Flagged IP: {ip_address} (count={flag_count}) for reason: {reason}"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to flag IP {ip_address} in Redis: {e}")
        return False


def is_ip_flagged(ip_address: str) -> bool:
    """
    Checks if an IP address is flagged by checking for the key's existence.
    """
    r = get_redis_connection(db_number=REDIS_DB_FLAGGED_IPS)
    if r:
        try:
            # FIX: r.exists() returns an int (0 or 1), not a bool. Cast it.
            return bool(r.exists(tenant_key(f"ip_flag:{ip_address}")))
        except Exception as e:
            logger.error(f"Failed to check IP {ip_address} in Redis: {e}")
            return False
    logger.error("Redis unavailable. Cannot check IP.")
    return False


def remove_ip_flag(ip_address: str):
    """
    Removes a flag from an IP address by deleting the key.
    """
    r = get_redis_connection(db_number=REDIS_DB_FLAGGED_IPS)
    if not r:
        logger.error("Redis unavailable. Cannot remove IP flag.")
        return False

    try:
        r.delete(tenant_key(f"ip_flag:{ip_address}"))
        r.delete(f"{FLAG_COUNT_PREFIX}{ip_address}")
        logger.info(f"Removed flag for IP: {ip_address}")
        return True
    except Exception as e:
        logger.error(f"Failed to remove IP flag for {ip_address}: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    # Example usage for direct testing of this module.
    print("Running IP Flagger example...")
    test_ip = "192.168.1.100"
    flag_suspicious_ip(test_ip, reason="Manual Test")
    print(f"Is {test_ip} flagged? {is_ip_flagged(test_ip)}")
    remove_ip_flag(test_ip)
    print(f"Is {test_ip} flagged after removal? {is_ip_flagged(test_ip)}")
