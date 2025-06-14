# anti_scrape/tarpit/tarpit_api.py
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
import asyncio
import httpx
import os
import random
import datetime
import sys
import logging
import hashlib
import redis # Added for hop limit check
from redis.exceptions import ConnectionError, RedisError

# --- Setup Logging ---
# Assuming basic logging is configured elsewhere or use:
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Import Local & Shared Modules ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from shared.honeypot_logger import log_honeypot_hit
    HONEYPOT_LOGGING_AVAILABLE = True
    logger.debug("Honeypot logger imported.")
except ImportError as e:
    logger.warning(f"Could not import shared.honeypot_logger: {e}. Honeypot hits will not be logged to dedicated file.")
    def log_honeypot_hit(details: dict): pass
    HONEYPOT_LOGGING_AVAILABLE = False

try:
    from .markov_generator import generate_dynamic_tarpit_page
    GENERATOR_AVAILABLE = True
    logger.debug("PostgreSQL Markov generator imported.")
except ImportError as e:
    logger.warning(f"Could not import markov_generator: {e}. Dynamic content generation disabled.")
    def generate_dynamic_tarpit_page() -> str:
        return "<html><body>Tarpit Error</body></html>"
    GENERATOR_AVAILABLE = False

try:
    from .ip_flagger import flag_suspicious_ip
    FLAGGING_AVAILABLE = True
    logger.debug("IP Flagger imported.")
except ImportError as e:
    logger.warning(f"Could not import ip_flagger: {e}. IP Flagging disabled.")
    def flag_suspicious_ip(ip_address: str) -> bool:
        return False
    FLAGGING_AVAILABLE = False

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
APP_ENV = os.getenv("APP_ENV", "production")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

if APP_ENV == "development" or DEBUG:
    logger.setLevel(logging.DEBUG) 
    logger.debug("Debug logging enabled.")
else:
    if LOG_LEVEL: logger.setLevel(LOG_LEVEL.upper())
    else:
        logger.setLevel(logging.INFO)
        LOG_LEVEL = "INFO"
    logger.debug(f"Log level set to {LOG_LEVEL}.")

# --- Configuration ---
ESCALATION_ENDPOINT = os.getenv("ESCALATION_ENDPOINT", "http://escalation_engine:8003/escalate")
MIN_STREAM_DELAY_SEC = float(os.getenv("TAR_PIT_MIN_DELAY_SEC", 0.6))
MAX_STREAM_DELAY_SEC = float(os.getenv("TAR_PIT_MAX_DELAY_SEC", 1.2))
SYSTEM_SEED = os.getenv("SYSTEM_SEED", "default_system_seed_value_change_me")

# Hop Limit Configuration
TAR_PIT_MAX_HOPS = int(os.getenv("TAR_PIT_MAX_HOPS", 250))
TAR_PIT_HOP_WINDOW_SECONDS = int(os.getenv("TAR_PIT_HOP_WINDOW_SECONDS", 86400)) # 24 hours
HOP_LIMIT_ENABLED = TAR_PIT_MAX_HOPS > 0

# Redis Configuration (Needs details for multiple DBs)
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD_FILE = os.getenv("REDIS_PASSWORD_FILE") # Optional password file path
REDIS_DB_TAR_PIT = int(os.getenv("REDIS_DB_TAR_PIT", 1))         # For visit flags
REDIS_DB_TAR_PIT_HOPS = int(os.getenv("REDIS_DB_TAR_PIT_HOPS", 4)) # For hop counts
REDIS_DB_BLOCKLIST = int(os.getenv("REDIS_DB_BLOCKLIST", 2))    # For triggering blocks
BLOCKLIST_TTL_SECONDS = int(os.getenv("BLOCKLIST_TTL_SECONDS", 86400))

# --- Redis Connection Pools ---
redis_password = None
if REDIS_PASSWORD_FILE and os.path.exists(REDIS_PASSWORD_FILE):
    try:
        with open(REDIS_PASSWORD_FILE, 'r') as f:
            redis_password = f.read().strip()
        logger.info("Loaded Redis password from file.")
    except Exception as e:
        logger.error(f"Failed to read Redis password from {REDIS_PASSWORD_FILE}: {e}")

try:
    # Pool for Tarpit Hop Counts (DB 4)
    redis_pool_hops = redis.ConnectionPool(
        host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB_TAR_PIT_HOPS,
        password=redis_password, decode_responses=True # Decode for easier handling
    )
    redis_hops = redis.Redis(connection_pool=redis_pool_hops)
    redis_hops.ping() # Test connection
    logger.info(f"Connected to Redis for Tarpit Hops (DB {REDIS_DB_TAR_PIT_HOPS})")

    # Pool for Blocklist writing (DB 2)
    redis_pool_blocklist = redis.ConnectionPool(
        host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB_BLOCKLIST,
        password=redis_password, decode_responses=True # Decode for easier handling
    )
    redis_blocklist = redis.Redis(connection_pool=redis_pool_blocklist)
    redis_blocklist.ping() # Test connection
    logger.info(f"Connected to Redis for Blocklist (DB {REDIS_DB_BLOCKLIST})")

    # Pool for IP Flagger (DB 1 - if flagger uses it)
    # Assuming ip_flagger manages its own connection based on env vars for now
    # If ip_flagger needs a shared pool, initialize it here too.
except ConnectionError as e:
    logger.error(f"FATAL: Could not connect to Redis at {REDIS_HOST}:{REDIS_PORT}. Tarpit hop/blocking features disabled. Error: {e}")
    # Disable features requiring Redis if connection fails
    HOP_LIMIT_ENABLED = False
    redis_hops = None
    redis_blocklist = None
    redis_blocklist = None
except Exception as e:
    logger.error(f"FATAL: Unexpected error setting up Redis connections: {e}", exc_info=True)
    HOP_LIMIT_ENABLED = False
    redis_hops = None
    redis_blocklist = None

# --- FastAPI App ---
app = FastAPI()

# --- Helper Functions ---
async def slow_stream_content(content: str):
    """Generator function to stream content slowly with randomized delays."""
    # Use the random state seeded by the handler
    lines = content.split('\n')
    for line in lines:
        yield line + '\n'
        delay = random.uniform(MIN_STREAM_DELAY_SEC, MAX_STREAM_DELAY_SEC)
        await asyncio.sleep(delay)

def trigger_ip_block(ip: str, reason: str):
    """Adds IP to the main Redis blocklist."""
    if not redis_blocklist:
        logger.error(f"Cannot block IP {ip}, Redis blocklist connection unavailable.")
        return False
    try:
        key = f"blocklist:{ip}"
        result = redis_blocklist.set(key, reason, ex=BLOCKLIST_TTL_SECONDS)
        if result:
            logger.warning(f"BLOCKED IP {ip} for {BLOCKLIST_TTL_SECONDS}s. Reason: {reason}")
            # Optionally increment a metric here
            # from metrics import increment_metric, METRIC_IP_BLOCKED_TARPIT_LIMIT
            # increment_metric(METRIC_IP_BLOCKED_TARPIT_LIMIT)
            return True
        else:
            logger.error(f"Failed to set blocklist key for IP {ip} in Redis.")
    except RedisError as e:
        logger.error(f"Redis error while trying to block IP {ip}: {e}")
        return False
        return False
    except Exception as e:
         logger.error(f"Unexpected error while blocking IP {ip}: {e}", exc_info=True)
         return False


# --- API Endpoints ---
@app.get("/tarpit/{path:path}", response_class=StreamingResponse, status_code=200)
async def tarpit_handler(request: Request, path: str = ""):
    """
    Handles requests redirected here. Logs hit, flags IP, checks hop limit,
    escalates metadata, and serves a slow, deterministically generated fake response.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    referer = request.headers.get("referer", "-")
    requested_path = str(request.url.path) # Full path including /tarpit/...
    http_method = request.method

    # --- Hop Limit Check ---
    if HOP_LIMIT_ENABLED and client_ip != "unknown" and redis_hops:
        try:
            hop_key = f"tarpit:hops:{client_ip}"
            # Use pipeline for atomic INCR and EXPIRE
            pipe = redis_hops.pipeline()
            pipe.incr(hop_key)
            pipe.expire(hop_key, TAR_PIT_HOP_WINDOW_SECONDS)
            results = pipe.execute()
            current_hop_count = results[0] # Result of INCR

            logger.debug(f"IP {client_ip} tarpit hop count: {current_hop_count}/{TAR_PIT_MAX_HOPS}")

            if current_hop_count > TAR_PIT_MAX_HOPS:
                logger.warning(f"Tarpit hop limit ({TAR_PIT_MAX_HOPS}) exceeded for IP: {client_ip}. Blocking IP.")
                block_reason = f"Tarpit hop limit exceeded ({current_hop_count} hits in {TAR_PIT_HOP_WINDOW_SECONDS}s)"
                trigger_ip_block(client_ip, block_reason)
                # Return an immediate 403 Forbidden response
                return HTMLResponse(
                    content="<html><head><title>Forbidden</title></head><body>Access Denied. Request frequency limit exceeded.</body></html>",
                    status_code=403
                )
        except RedisError as e:
            logger.error(f"Redis error during hop limit check for IP {client_ip}: {e}")
            # Fail open: If Redis check fails, proceed with serving the tarpit
        except Exception as e:
            logger.error(f"Unexpected error during hop limit check for IP {client_ip}: {e}", exc_info=True)
            # Fail open


    # --- Standard Tarpit Operations (Log, Flag, Escalate) ---
    logger.info(f"TAR_PIT HIT: Path={requested_path}, IP={client_ip}, UA='{user_agent}'")
    honeypot_details = {
        "ip": client_ip, "user_agent": user_agent, "method": http_method,
        "path": requested_path, "referer": referer, "headers": dict(request.headers)
    }
    if HONEYPOT_LOGGING_AVAILABLE:
        try: log_honeypot_hit(honeypot_details)
        except Exception as e: logger.error(f"Error logging honeypot hit: {e}", exc_info=True)

    if FLAGGING_AVAILABLE:
        try: flag_suspicious_ip(client_ip)
        except Exception as e: logger.error(f"Error flagging IP {client_ip}: {e}", exc_info=True)

    timestamp_iso = datetime.datetime.utcnow().isoformat() + "Z"
    metadata = {
        "timestamp": timestamp_iso, "ip": client_ip, "user_agent": user_agent,
        "referer": referer, "path": requested_path, "headers": dict(request.headers),
        "source": "tarpit_api"
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(ESCALATION_ENDPOINT, json=metadata, timeout=5.0)
            if response.status_code >= 400:
                 logger.warning(f"Escalation request for IP {client_ip} failed with status {response.status_code}. Response: {response.text[:200]}")
    except Exception as e:
        logger.error(f"Error escalating request for IP {client_ip} to {ESCALATION_ENDPOINT}: {e}", exc_info=True)

    # --- Deterministic Response Generation ---
    content = "<html><body>Tarpit Error</body></html>" # Default fallback
    if GENERATOR_AVAILABLE:
        try:
            path_bytes = requested_path.encode('utf-8')
            path_hash = hashlib.sha256(path_bytes).hexdigest()
            combined_seed = f"{SYSTEM_SEED}-{path_hash}"
            random.seed(combined_seed)
            logger.debug(f"Seeded RNG for path '{requested_path}' with combined seed.")
            content = generate_dynamic_tarpit_page()
        except Exception as e:
            logger.error(f"Error generating dynamic page for path '{requested_path}': {e}", exc_info=True)
            content = "<html><head><title>Error</title></head><body>Service temporarily unavailable. Please try again later.</body></html>"
    else:
        content = """<!DOCTYPE html>
<html><head><title>Loading Resource...</title><meta name="robots" content="noindex, nofollow"></head>
<body><h1>Please wait</h1><p>Your content is loading slowly...</p><progress></progress>
</body></html>"""

    # --- Stream the response slowly ---
    media_type = "text/html"
    return StreamingResponse(slow_stream_content(content), media_type=media_type)


# --- Root/Health Check (Optional but recommended) ---
@app.get("/health")
async def health_check():
    """ Basic health check endpoint for the Tarpit API. """
    db_ok = False
    # Check PG connectivity (assuming generator is available)
    if GENERATOR_AVAILABLE:
        try:
            # Requires markov_generator to expose a connection check or use a shared pool
            # For now, assume generator handles its own checks/errors
             db_ok = True # Simplified check
        except Exception:
            db_ok = False
    # Check Redis connectivity
    redis_hops_ok = False
    redis_blocklist_ok = False
    try:
        if redis_hops: redis_hops_ok = redis_hops.ping()
    except Exception: redis_hops_ok = False
    try:
        if redis_blocklist: redis_blocklist_ok = redis_blocklist.ping()
    except Exception: redis_blocklist_ok = False

    status = "ok" if redis_hops_ok and redis_blocklist_ok else "error"

    return {
        "status": status,
        "generator_available": GENERATOR_AVAILABLE,
        "postgres_connected": db_ok, # Placeholder
        "redis_hops_connected": redis_hops_ok,
        "redis_blocklist_connected": redis_blocklist_ok,
        "hop_limit_enabled": HOP_LIMIT_ENABLED,
        "max_hops_config": TAR_PIT_MAX_HOPS if HOP_LIMIT_ENABLED else "disabled"
    }

@app.get("/")
async def root():
     """ Basic info endpoint """
     return {"message": "AntiScrape Tarpit API"}


if __name__ == "__main__":
    import uvicorn
    logger.info("--- Tarpit API Starting ---")
    logger.info(f"Escalation Endpoint: {ESCALATION_ENDPOINT}")
    logger.info(f"Generator Available: {GENERATOR_AVAILABLE}")
    logger.info(f"IP Flagging Available: {FLAGGING_AVAILABLE}")
    logger.info(f"System Seed Loaded: {'Yes' if SYSTEM_SEED else 'No (Using Default)'}")
    logger.info(f"Hop Limit Enabled: {HOP_LIMIT_ENABLED} (Max Hops: {TAR_PIT_MAX_HOPS}, Window: {TAR_PIT_HOP_WINDOW_SECONDS}s, DB: {REDIS_DB_TAR_PIT_HOPS})")
    logger.info(f"Redis Blocklist DB for Trigger: {REDIS_DB_BLOCKLIST}")
    logger.info(f"Streaming Delay: {MIN_STREAM_DELAY_SEC:.2f}s - {MAX_STREAM_DELAY_SEC:.2f}s")
    logger.info("--------------------------")
    # Determine number of workers based on environment or default
    port = int(os.getenv("TARPIT_API_PORT", 8005))
    workers = int(os.getenv("UVICORN_WORKERS", 2))
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    
    logger.info(f"Starting Tarpit API on port {port}")
    uvicorn.run(
        "tarpit_api:app",
        host="0.0.0.0",
        port=port,
        workers=workers,
        log_level=log_level
    )
    logger.info("--- Tarpit API Started ---")