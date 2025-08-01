# anti_scrape/tarpit/tarpit_api.py
import asyncio
import datetime
import hashlib
import logging
import os
import random
import sys
from typing import Dict

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

# The direct 'redis' import is no longer needed as the client handles it.
from redis.exceptions import RedisError

# --- Setup Logging ---
# Preserved from your original file.
from src.shared.config import CONFIG, tenant_key
from src.shared.redis_client import get_redis_connection

from .bad_api_generator import register_bad_endpoints

logging.basicConfig(
    level=CONFIG.LOG_LEVEL.upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# --- Import Local & Shared Modules (Preserved from your original file) ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from shared.honeypot_logger import log_honeypot_hit

    HONEYPOT_LOGGING_AVAILABLE = True
    logger.debug("Honeypot logger imported.")
except ImportError as e:
    logger.warning(
        f"Could not import shared.honeypot_logger: {e}. Honeypot hits will not be logged to dedicated file."
    )

    def log_honeypot_hit(details: dict):
        pass

    HONEYPOT_LOGGING_AVAILABLE = False

try:
    from tarpit_rs import generate_dynamic_tarpit_page

    GENERATOR_AVAILABLE = True
    logger.debug("Rust Markov generator imported.")
except ImportError as e:
    logger.warning(
        f"Could not import tarpit_rs: {e}. Falling back to Python implementation."
    )
    try:
        from .markov_generator import generate_dynamic_tarpit_page

        GENERATOR_AVAILABLE = True
        logger.debug("Python Markov generator imported as fallback.")
    except ImportError as e2:
        logger.warning(
            f"Could not import markov_generator: {e2}. Dynamic content generation disabled."
        )

        def generate_dynamic_tarpit_page() -> str:
            return "<html><body>Tarpit Error</body></html>"

        GENERATOR_AVAILABLE = False

try:
    from .labyrinth import generate_labyrinth_page

    LABYRINTH_AVAILABLE = True
except Exception:
    LABYRINTH_AVAILABLE = False

try:
    # Uses the corrected ip_flagger with the renamed function
    from .ip_flagger import flag_suspicious_ip, is_ip_flagged

    FLAGGING_AVAILABLE = True
    logger.debug("IP Flagger imported.")
except ImportError as e:
    logger.warning(f"Could not import ip_flagger: {e}. IP Flagging disabled.")

    def flag_suspicious_ip(ip_address: str, reason: str) -> bool:
        return False

    def is_ip_flagged(ip_address: str) -> bool:
        return False

    FLAGGING_AVAILABLE = False

# --- Environment-based Logging (Preserved from your original file) ---
LOG_LEVEL = CONFIG.LOG_LEVEL
APP_ENV = CONFIG.APP_ENV
DEBUG = CONFIG.DEBUG

if APP_ENV == "development" or DEBUG:
    logger.setLevel(logging.DEBUG)
    logger.debug("Debug logging enabled.")
else:
    if LOG_LEVEL:
        logger.setLevel(LOG_LEVEL.upper())
    else:
        logger.setLevel(logging.INFO)
        LOG_LEVEL = "INFO"
    logger.debug(f"Log level set to {LOG_LEVEL}.")

# --- Configuration (Preserved from your original file) ---
ESCALATION_ENDPOINT = CONFIG.ESCALATION_ENDPOINT
MIN_STREAM_DELAY_SEC = CONFIG.TAR_PIT_MIN_DELAY_SEC
MAX_STREAM_DELAY_SEC = CONFIG.TAR_PIT_MAX_DELAY_SEC
SYSTEM_SEED = CONFIG.SYSTEM_SEED

TAR_PIT_MAX_HOPS = CONFIG.TAR_PIT_MAX_HOPS
TAR_PIT_HOP_WINDOW_SECONDS = CONFIG.TAR_PIT_HOP_WINDOW_SECONDS
HOP_LIMIT_ENABLED = TAR_PIT_MAX_HOPS > 0

REDIS_DB_TAR_PIT_HOPS = CONFIG.REDIS_DB_TAR_PIT_HOPS
REDIS_DB_BLOCKLIST = CONFIG.REDIS_DB_BLOCKLIST
BLOCKLIST_TTL_SECONDS = CONFIG.BLOCKLIST_TTL_SECONDS
ENABLE_TARPIT_CATCH_ALL = CONFIG.ENABLE_TARPIT_CATCH_ALL


# --- THIS IS THE SOLE REFACTORING CHANGE ---
# Replaced the manual Redis Connection Pools with calls to the centralized client.
redis_hops = get_redis_connection(db_number=REDIS_DB_TAR_PIT_HOPS)
redis_blocklist = get_redis_connection(db_number=REDIS_DB_BLOCKLIST)

if not redis_hops or not redis_blocklist:
    logger.error(
        "FATAL: Could not connect to one or more Redis databases. Tarpit features may be degraded."
    )
    HOP_LIMIT_ENABLED = False
# --- END OF REFACTORING CHANGE ---


# --- FastAPI App ---
app = FastAPI()
BAD_API_ENDPOINTS = register_bad_endpoints(app)


# --- Helper Functions (Preserved from your original file) ---
async def slow_stream_content(content: str):
    lines = content.split("\n")
    for line in lines:
        yield line + "\n"
        delay = random.uniform(MIN_STREAM_DELAY_SEC, MAX_STREAM_DELAY_SEC)
        await asyncio.sleep(delay)


def trigger_ip_block(ip: str, reason: str):
    if not redis_blocklist:
        logger.error(f"Cannot block IP {ip}, Redis blocklist connection unavailable.")
        return False
    try:
        key = tenant_key(f"blocklist:{ip}")
        if redis_blocklist.exists(key):
            logger.info(f"IP {ip} already in blocklist. TTL refreshed")
        result = redis_blocklist.setex(key, BLOCKLIST_TTL_SECONDS, reason)
        if result:
            logger.warning(
                f"BLOCKED IP {ip} for {BLOCKLIST_TTL_SECONDS}s. Reason: {reason}"
            )
            return True
        else:
            logger.error(f"Failed to set blocklist key for IP {ip} in Redis.")
            return False
    except RedisError as e:
        logger.error(f"Redis error while trying to block IP {ip}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error while blocking IP {ip}: {e}", exc_info=True)
        return False


SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie"}


def sanitize_headers(headers: Dict[str, str]) -> Dict[str, str]:
    sanitized: Dict[str, str] = {}
    for k, v in headers.items():
        if k.lower() in SENSITIVE_HEADERS:
            continue
        sanitized[k] = str(v).replace("\n", " ").replace("\r", " ")
    return sanitized


# --- API Endpoints (Preserved from your original file) ---
@app.get("/tarpit/{path:path}", response_class=StreamingResponse, status_code=200)
async def tarpit_handler(request: Request, path: str = ""):
    if not ENABLE_TARPIT_CATCH_ALL and path:
        raise HTTPException(status_code=404)
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    referer = request.headers.get("referer", "-")
    requested_path = str(request.url.path)
    http_method = request.method

    if HOP_LIMIT_ENABLED and client_ip != "unknown" and redis_hops:
        try:
            if not is_ip_flagged(client_ip):
                logger.debug(f"IP {client_ip} not flagged; hop count not enforced")
            else:
                hop_key = tenant_key(f"tarpit:hops:{client_ip}")
                pipe = redis_hops.pipeline()
                pipe.incr(hop_key)
                pipe.expire(hop_key, TAR_PIT_HOP_WINDOW_SECONDS)
                results = pipe.execute()
                current_hop_count = results[0]

                logger.debug(
                    f"IP {client_ip} tarpit hop count: {current_hop_count}/{TAR_PIT_MAX_HOPS}"
                )

                if current_hop_count > TAR_PIT_MAX_HOPS:
                    logger.warning(
                        f"Tarpit hop limit ({TAR_PIT_MAX_HOPS}) exceeded for IP: {client_ip}. Blocking IP."
                    )
                    block_reason = f"Tarpit hop limit exceeded ({current_hop_count} hits in {TAR_PIT_HOP_WINDOW_SECONDS}s)"
                    trigger_ip_block(client_ip, block_reason)
                    return HTMLResponse(
                        content="<html><head><title>Forbidden</title></head><body>Access Denied.</body></html>",
                        status_code=403,
                    )
        except RedisError as e:
            logger.error(f"Redis error during hop limit check for IP {client_ip}: {e}")
        except Exception as e:
            logger.error(
                f"Unexpected error during hop limit check for IP {client_ip}: {e}",
                exc_info=True,
            )

    logger.info(
        f"TAR_PIT HIT: Path={requested_path}, IP={client_ip}, UA='{user_agent}'"
    )
    honeypot_details = {
        "ip": client_ip,
        "user_agent": user_agent,
        "method": http_method,
        "path": requested_path,
        "referer": referer,
        "headers": sanitize_headers(dict(request.headers)),
    }
    if HONEYPOT_LOGGING_AVAILABLE:
        try:
            log_honeypot_hit(honeypot_details)
        except Exception as e:
            logger.error(f"Error logging honeypot hit: {e}", exc_info=True)

    if FLAGGING_AVAILABLE:
        try:
            flag_suspicious_ip(ip_address=client_ip, reason="Tarpit Hit")
        except Exception as e:
            logger.error(f"Error flagging IP {client_ip}: {e}", exc_info=True)

    timestamp_iso = (
        datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    )
    metadata = {
        "timestamp": timestamp_iso,
        "ip": client_ip,
        "user_agent": user_agent,
        "referer": referer,
        "method": http_method,
        "path": requested_path,
        "headers": sanitize_headers(dict(request.headers)),
        "source": "tarpit_api",
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                ESCALATION_ENDPOINT, json=metadata, timeout=5.0
            )
            if response.status_code >= 400:
                logger.warning(
                    "Escalation request for IP %s failed with status %s. Response: %s",
                    client_ip,
                    response.status_code,
                    response.text[:200],
                )
    except Exception as e:
        logger.error(
            "Error escalating request for IP %s to %s: %s",
            client_ip,
            ESCALATION_ENDPOINT,
            e,
            exc_info=True,
        )

    content = "<html><body>Tarpit Error</body></html>"
    if CONFIG.ENABLE_AI_LABYRINTH and LABYRINTH_AVAILABLE:
        try:
            path_bytes = requested_path.encode("utf-8")
            path_hash = hashlib.sha256(path_bytes).hexdigest()
            combined_seed = f"{SYSTEM_SEED}-{path_hash}"
            content = generate_labyrinth_page(
                combined_seed, depth=CONFIG.TARPIT_LABYRINTH_DEPTH
            )
        except Exception as e:
            logger.error(
                f"Error generating labyrinth page for path '{requested_path}': {e}",
                exc_info=True,
            )
    elif GENERATOR_AVAILABLE:
        try:
            path_bytes = requested_path.encode("utf-8")
            path_hash = hashlib.sha256(path_bytes).hexdigest()
            combined_seed = f"{SYSTEM_SEED}-{path_hash}"
            random.seed(combined_seed)
            logger.debug(f"Seeded RNG for path '{requested_path}' with combined seed.")
            content = generate_dynamic_tarpit_page()
        except Exception as e:
            logger.error(
                f"Error generating dynamic page for path '{requested_path}': {e}",
                exc_info=True,
            )
            content = "<html><head><title>Error</title></head><body>Service temporarily unavailable.</body></html>"
    else:
        content = """<!DOCTYPE html>
<html><head><title>Loading Resource...</title><meta name="robots" content="noindex, nofollow"></head>
<body><h1>Please wait</h1><p>Your content is loading slowly...</p><progress></progress>
</body></html>"""

    return StreamingResponse(slow_stream_content(content), media_type="text/html")


@app.get("/health")
async def health_check():
    db_ok = True if GENERATOR_AVAILABLE else False
    redis_hops_ok = False
    redis_blocklist_ok = False
    try:
        if redis_hops:
            redis_hops_ok = redis_hops.ping()
    except Exception:
        redis_hops_ok = False
    try:
        if redis_blocklist:
            redis_blocklist_ok = redis_blocklist.ping()
    except Exception:
        redis_blocklist_ok = False

    status = "ok" if redis_hops_ok and redis_blocklist_ok else "error"
    return {
        "status": status,
        "generator_available": GENERATOR_AVAILABLE,
        "postgres_connected": db_ok,
        "redis_hops_connected": redis_hops_ok,
        "redis_blocklist_connected": redis_blocklist_ok,
        "hop_limit_enabled": HOP_LIMIT_ENABLED,
        "max_hops_config": TAR_PIT_MAX_HOPS if HOP_LIMIT_ENABLED else "disabled",
    }


@app.get("/")
async def root():
    return {"message": "AntiScrape Tarpit API"}


if __name__ == "__main__":
    import uvicorn

    logger.info("--- Tarpit API Starting ---")
    logger.info(f"Escalation Endpoint: {ESCALATION_ENDPOINT}")
    logger.info(f"Generator Available: {GENERATOR_AVAILABLE}")
    logger.info(f"IP Flagging Available: {FLAGGING_AVAILABLE}")
    seed_loaded = (
        "Yes"
        if SYSTEM_SEED != "default_system_seed_value_change_me"
        else "No (Using Default)"
    )
    logger.info("System Seed Loaded: %s", seed_loaded)
    logger.info(
        "Hop Limit Enabled: %s (Max Hops: %s, Window: %ss, DB: %s)",
        HOP_LIMIT_ENABLED,
        TAR_PIT_MAX_HOPS,
        TAR_PIT_HOP_WINDOW_SECONDS,
        REDIS_DB_TAR_PIT_HOPS,
    )
    logger.info(f"Redis Blocklist DB for Trigger: {REDIS_DB_BLOCKLIST}")
    logger.info(
        f"Streaming Delay: {MIN_STREAM_DELAY_SEC:.2f}s - {MAX_STREAM_DELAY_SEC:.2f}s"
    )
    logger.info("--------------------------")
    port = CONFIG.TARPIT_API_PORT
    workers = int(os.getenv("UVICORN_WORKERS", 2))
    log_level = CONFIG.LOG_LEVEL.lower()

    logger.info(f"Starting Tarpit API on port {port}")
    uvicorn.run(
        "tarpit_api:app",
        host=os.getenv("TARPIT_HOST", "127.0.0.1"),
        port=port,
        workers=workers,
        log_level=log_level,
    )
