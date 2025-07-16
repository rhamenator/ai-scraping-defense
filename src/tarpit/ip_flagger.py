"""
This module provides functions to flag, check, and remove IP addresses
in a dedicated Redis database. It uses a centralized Redis connection
utility from the 'shared' module.
"""
import sys
import logging
from src.shared.redis_client import get_redis_connection

# Configure logging for this module
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define the specific Redis database number for flagged IPs.
REDIS_DB_FLAGGED_IPS = 3

def flag_suspicious_ip(ip_address: str, reason: str = "Suspicious activity"):
    """
    Flags an IP address by setting a key in Redis.
    Connects to the dedicated database for flagged IPs.
    (Formerly flag_ip)
    """
    r = get_redis_connection(db_number=REDIS_DB_FLAGGED_IPS)
    if r:
        try:
            r.set(f"ip_flag:{ip_address}", reason)
            logging.info(f"Flagged IP: {ip_address} for reason: {reason}")
            return True
        except Exception as e:
            logging.error(f"Failed to flag IP {ip_address} in Redis: {e}")
            return False
    return False


def is_ip_flagged(ip_address: str) -> bool:
    """
    Checks if an IP address is flagged by checking for the key's existence.
    """
    r = get_redis_connection(db_number=REDIS_DB_FLAGGED_IPS)
    if r:
        try:
            # FIX: r.exists() returns an int (0 or 1), not a bool. Cast it.
            return bool(r.exists(f"ip_flag:{ip_address}"))
        except Exception as e:
            logging.error(f"Failed to check IP {ip_address} in Redis: {e}")
            return False
    return False


def remove_ip_flag(ip_address: str):
    """
    Removes a flag from an IP address by deleting the key.
    """
    r = get_redis_connection(db_number=REDIS_DB_FLAGGED_IPS)
    if r:
        try:
            r.delete(f"ip_flag:{ip_address}")
            logging.info(f"Removed flag for IP: {ip_address}")
            return True
        except Exception as e:
            logging.error(f"Failed to remove flag for IP {ip_address} in Redis: {e}")
            return False
    return False
if __name__ == '__main__':
    # Example usage for direct testing of this module.
    print("Running IP Flagger example...")
    test_ip = "192.168.1.100"
    flag_suspicious_ip(test_ip, reason="Manual Test")
    print(f"Is {test_ip} flagged? {is_ip_flagged(test_ip)}")
    remove_ip_flag(test_ip)
    print(f"Is {test_ip} flagged after removal? {is_ip_flagged(test_ip)}")
