"""Convenience functions for creating Redis connections."""
import redis
import os
import logging

def get_redis_connection(db_number=0):
    """
    Creates and returns a Redis connection using environment variables for configuration.
    Handles password loading from a file.
    """
    redis_host = os.environ.get("REDIS_HOST", "localhost")
    password = None

    if password_file := os.environ.get("REDIS_PASSWORD_FILE"):
        try:
            with open(password_file, 'r') as f:
                password = f.read().strip()
        except FileNotFoundError:
            logging.error(f"Redis password file not found at {password_file}")
            return None
    
    redis_port = int(os.environ.get("REDIS_PORT", 6379))

    try:
        r = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=password,
            db=db_number,
            decode_responses=True  # Decode responses to UTF-8 by default
        )
        r.ping()
        logging.info(f"Successfully connected to Redis at {redis_host} on DB {db_number}")
        return r
    except redis.AuthenticationError:
        logging.error(f"Redis authentication failed for DB {db_number}. Check password.")
        return None
    except Exception as e:
        logging.error(f"Failed to connect to Redis at {redis_host} on DB {db_number}: {e}")
        return None
