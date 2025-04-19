# tarpit/ip_flagger.py
# Utility for flagging suspicious IP addresses using Redis

import redis
import os
import datetime

# --- Redis Configuration ---
REDIS_HOST = os.getenv("REDIS_HOST", "redis") # Assumes 'redis' service name from docker-compose
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB_TAR PIT", 1)) # Use a separate DB for tarpit flags
FLAG_TTL_SECONDS = int(os.getenv("TAR PIT_FLAG_TTL", 300)) # Time-to-live for an IP flag (e.g., 5 minutes)
MAX_FLAGS_PER_IP = int(os.getenv("TAR PIT_MAX_FLAGS", 5)) # Max flags before longer action? (Optional)

try:
    # Use connection pooling for efficiency
    redis_pool = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    redis_client = redis.Redis(connection_pool=redis_pool)
    redis_client.ping() # Test connection on import
    print(f"Connected to Redis for IP flagging at {REDIS_HOST}:{REDIS_PORT}, DB: {REDIS_DB}")
except redis.exceptions.ConnectionError as e:
    print(f"ERROR: Could not connect to Redis at {REDIS_HOST}:{REDIS_PORT}. IP Flagging disabled. Error: {e}")
    redis_client = None # Disable flagging if Redis is unavailable

def flag_suspicious_ip(ip_address: str):
    """
    Flags an IP address in Redis with a specific TTL.
    Increments a counter for the IP.
    """
    if not redis_client or not ip_address:
        return False # Do nothing if Redis is unavailable or IP is invalid

    try:
        # Use a key like 'tarpit_flag:<ip_address>'
        flag_key = f"tarpit_flag:{ip_address}"
        # Set the flag with an expiration time (TTL)
        # The value could be a timestamp or simply '1'
        timestamp = datetime.datetime.utcnow().isoformat()
        redis_client.setex(flag_key, FLAG_TTL_SECONDS, timestamp)

        # Optional: Implement a counter for repeated offenses
        # counter_key = f"tarpit_count:{ip_address}"
        # current_count = redis_client.incr(counter_key)
        # redis_client.expire(counter_key, FLAG_TTL_SECONDS * 2) # Expire counter slightly longer than flag
        # if current_count > MAX_FLAGS_PER_IP:
        #     print(f"WARNING: IP {ip_address} flagged {current_count} times. Consider longer ban.")

        print(f"Flagged IP: {ip_address} in Redis for {FLAG_TTL_SECONDS} seconds.")
        return True
    except redis.exceptions.RedisError as e:
        print(f"ERROR: Redis error while flagging IP {ip_address}: {e}")
        return False
    except Exception as e:
        print(f"ERROR: Unexpected error flagging IP {ip_address}: {e}")
        return False

def check_ip_flag(ip_address: str) -> bool:
    """
    Checks if an IP address is currently flagged in Redis.
    """
    if not redis_client or not ip_address:
        return False

    try:
        flag_key = f"tarpit_flag:{ip_address}"
        return redis_client.exists(flag_key) > 0
    except redis.exceptions.RedisError as e:
        print(f"ERROR: Redis error while checking IP flag {ip_address}: {e}")
        return False # Fail safe (assume not flagged if error)
    except Exception as e:
        print(f"ERROR: Unexpected error checking IP flag {ip_address}: {e}")
        return False

# Example usage (for testing this module directly)
# if __name__ == "__main__":
#    test_ip = "192.168.1.100"
#    print(f"Checking flag for {test_ip}: {check_ip_flag(test_ip)}")
#    print(f"Flagging {test_ip}...")
#    flag_suspicious_ip(test_ip)
#    print(f"Checking flag for {test_ip}: {check_ip_flag(test_ip)}")