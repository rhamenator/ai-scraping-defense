import os
import time
import logging
from typing import List, Optional

from src.shared.redis_client import get_redis_connection
from src.util import compute_rate_limit
from src.shared.config import tenant_key

REDIS_DB_FREQUENCY = int(os.getenv("REDIS_DB_FREQUENCY", 3))
FREQUENCY_KEY_PREFIX = os.getenv("FREQUENCY_KEY_PREFIX") or tenant_key("freq:")
FREQUENCY_WINDOW_SECONDS = int(os.getenv("ADAPTIVE_RATE_WINDOW_SECONDS", 60))
BASE_RATE_LIMIT = int(os.getenv("BASE_RATE_LIMIT", 60))
NGINX_RATE_LIMIT_CONF = os.getenv(
    "NGINX_RATE_LIMIT_CONF", "/etc/nginx/conf.d/req_rate_limit.conf"
)

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def get_recent_counts(redis_conn, window_seconds: int) -> List[int]:
    """Return request counts per IP within the given window."""
    now = time.time()
    start = now - window_seconds
    counts: List[int] = []
    try:
        for key in redis_conn.scan_iter(match=f"{FREQUENCY_KEY_PREFIX}*"):
            count = redis_conn.zcount(key, start, now)
            if isinstance(count, int):
                counts.append(count)
    except Exception as exc:  # pragma: no cover - unexpected redis errors
        logger.error("Error reading frequency data: %s", exc)
    return counts


def update_rate_limit(new_limit: int) -> bool:
    """Write the limit_req configuration for Nginx."""
    line = f"limit_req_zone $binary_remote_addr zone=req_rate_limit:10m rate={new_limit}r/m;"
    try:
        with open(NGINX_RATE_LIMIT_CONF, "w", encoding="utf-8") as f:
            f.write(line + "\n")
        logger.info("Wrote new Nginx rate limit: %sr/m", new_limit)
        return True
    except Exception as exc:  # pragma: no cover - file system issues
        logger.error("Failed to write Nginx rate limit config: %s", exc)
        return False


def compute_and_update(redis_conn: Optional[object] = None) -> int:
    """Compute a new rate limit from recent counts and update Nginx."""
    if redis_conn is None:
        redis_conn = get_redis_connection(db_number=REDIS_DB_FREQUENCY)
    if not redis_conn:
        logger.error("Redis unavailable, cannot update rate limit.")
        return BASE_RATE_LIMIT

    counts = get_recent_counts(redis_conn, FREQUENCY_WINDOW_SECONDS)
    new_limit = compute_rate_limit(counts, BASE_RATE_LIMIT)
    update_rate_limit(new_limit)
    return new_limit


if __name__ == "__main__":  # pragma: no cover - manual execution
    compute_and_update()
