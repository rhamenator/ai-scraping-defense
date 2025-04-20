from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
import asyncio
import httpx
import os
import random
import datetime
import sys
import logging # Added for better logging

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Import Local & Shared Modules ---
# Assuming shared/ is one level up from tarpit/ or accessible via PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from shared.honeypot_logger import log_honeypot_hit # Import the dedicated logger function
    HONEYPOT_LOGGING_AVAILABLE = True
    logger.info("Honeypot logger imported successfully.")
except ImportError as e:
    logger.warning(f"Could not import shared.honeypot_logger: {e}. Honeypot hits will not be logged to dedicated file.")
    def log_honeypot_hit(details: dict): pass # Dummy function
    HONEYPOT_LOGGING_AVAILABLE = False

try:
    from .markov_generator import generate_dynamic_tarpit_page
    GENERATOR_AVAILABLE = True
    logger.info("Markov generator imported successfully.")
except ImportError as e:
    logger.warning(f"Could not import markov_generator: {e}. Dynamic content generation disabled.")
    GENERATOR_AVAILABLE = False

try:
    from .ip_flagger import flag_suspicious_ip # Assuming ip_flagger is in the same directory
    FLAGGING_AVAILABLE = True
    logger.info("IP Flagger imported successfully.")
except ImportError as e:
    logger.warning(f"Could not import ip_flagger: {e}. IP Flagging disabled.")
    def flag_suspicious_ip(ip: str): pass # Dummy function
    FLAGGING_AVAILABLE = False


# --- Configuration ---
ESCALATION_ENDPOINT = os.getenv("ESCALATION_ENDPOINT", "http://escalation_engine:8003/escalate")
MIN_STREAM_DELAY_SEC = 0.6 # Minimum delay between yielded lines
MAX_STREAM_DELAY_SEC = 1.2 # Maximum delay between yielded lines

# --- FastAPI App ---
app = FastAPI()

# --- Helper Functions ---
async def slow_stream_content(content: str):
    """Generator function to stream content slowly with randomized delays."""
    # Consider adding small initial delay too
    # await asyncio.sleep(random.uniform(0.1, 0.5))
    lines = content.split('\n')
    for line in lines:
        yield line + '\n'
        # Randomize delay within configured bounds
        delay = random.uniform(MIN_STREAM_DELAY_SEC, MAX_STREAM_DELAY_SEC)
        await asyncio.sleep(delay)

# --- API Endpoints ---
# Define catch-all routes for tarpit paths
@app.get("/tarpit", response_class=StreamingResponse, status_code=200)
@app.get("/tarpit/{path:path}", response_class=StreamingResponse, status_code=200)
# Can add POST etc. if needed, but GET is primary for simple bots/scrapers
async def tarpit_handler(request: Request, path: str = None):
    """
    Handles requests redirected here (potential honeypot triggers).
    Logs the hit, flags IP, escalates metadata, and serves a slow, fake response.
    NOTE: Consider varying status_code sometimes (e.g., 503, 429) instead of always 200.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    referer = request.headers.get("referer", "-")
    requested_path = str(request.url.path) # Full path including /tarpit/..
    http_method = request.method

    # Log the hit as a honeypot event
    logger.info(f"TAR PIT HIT: Path={requested_path}, IP={client_ip}, UA='{user_agent}'") # Keep console log
    honeypot_details = {
        "ip": client_ip,
        "user_agent": user_agent,
        "method": http_method,
        "path": requested_path,
        "referer": referer,
        "headers": dict(request.headers) # Log headers for context
    }
    if HONEYPOT_LOGGING_AVAILABLE:
        try:
            log_honeypot_hit(honeypot_details) # Call the dedicated logger
        except Exception as e:
             logger.error(f"Error calling honeypot logger for {client_ip}: {e}", exc_info=True)

    # --- IP Flagging ---
    if FLAGGING_AVAILABLE:
        try:
            flag_suspicious_ip(client_ip)
        except Exception as e:
            logger.error(f"Error during IP flagging for {client_ip}: {e}", exc_info=True)

    # --- Escalation ---
    # Prepare metadata ensuring datetime is ISO formatted string
    timestamp_iso = datetime.datetime.utcnow().isoformat() + "Z"
    metadata = {
        "timestamp": timestamp_iso,
        "ip": client_ip,
        "user_agent": user_agent,
        "referer": referer,
        "path": requested_path,
        "headers": dict(request.headers),
        "source": "tarpit_api"
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(ESCALATION_ENDPOINT, json=metadata, timeout=5.0)
            # Check response status, log if escalation failed
            if response.status_code >= 400:
                 logger.warning(f"Escalation request for IP {client_ip} failed with status {response.status_code}. Response: {response.text[:200]}")
            response.raise_for_status() # Raise exception for >= 400
    except httpx.RequestError as exc:
        logger.error(f"Error escalating request for IP {client_ip} to {ESCALATION_ENDPOINT}: {exc}")
    except Exception as e:
        logger.error(f"Unexpected error during escalation for IP {client_ip}: {e}", exc_info=True)

    # --- Response Generation ---
    # Monitor resource usage (CPU/Memory/Network IO) of this service under load.
    # If streaming ties up too many workers, consider alternative strategies
    # like serving a static page with client-side JS delays/infinite loops.
    if GENERATOR_AVAILABLE:
        try:
            content = generate_dynamic_tarpit_page()
        except Exception as e:
            logger.error(f"Error generating dynamic page: {e}", exc_info=True)
            # Fallback static content
            content = "<html><head><title>Error</title></head><body>Service temporarily unavailable. Please try again later.</body></html>"
    else:
        # Default static content if generator is unavailable
        content = """<!DOCTYPE html>
<html><head><title>Loading Resource...</title><meta name="robots" content="noindex, nofollow"></head>
<body><h1>Please wait</h1><p>Your content is loading slowly...</p><progress></progress>
</body></html>"""

    # --- Stream the response slowly ---
    # Choose a random media type? text/html, application/javascript, text/plain?
    media_type = "text/html"
    return StreamingResponse(slow_stream_content(content), media_type=media_type)


# --- Root/Health Check (Optional) ---
@app.get("/")
async def root():
    """ Basic health check endpoint """
    return {"status": "Tarpit API is running"}


if __name__ == "__main__":
    import uvicorn
    logger.info("--- Tarpit API Starting ---")
    logger.info(f"Escalation Endpoint: {ESCALATION_ENDPOINT}")
    logger.info(f"Dynamic Content Generation: {'Enabled' if GENERATOR_AVAILABLE else 'Disabled'}")
    logger.info(f"IP Flagging: {'Enabled' if FLAGGING_AVAILABLE else 'Disabled'}")
    logger.info("--------------------------")
    # Use reload=True only for development
    uvicorn.run(app, host="0.0.0.0", port=8001)