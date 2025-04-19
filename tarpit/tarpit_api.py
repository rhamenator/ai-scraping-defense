from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
import asyncio
import httpx
import os
import random
import datetime
import sys

# --- Import Local & Shared Modules ---
# Assuming shared/ is one level up from tarpit/ or accessible via PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from shared.honeypot_logger import log_honeypot_hit # Import the new logger function
    HONEYPOT_LOGGING_AVAILABLE = True
except ImportError:
    print("Warning: Could not import shared.honeypot_logger. Honeypot hits will not be logged to dedicated file.")
    def log_honeypot_hit(details: dict): pass # Dummy function
    HONEYPOT_LOGGING_AVAILABLE = False

try:
    from .markov_generator import generate_dynamic_tarpit_page
    GENERATOR_AVAILABLE = True
except ImportError:
    print("Warning: Could not import markov_generator. Dynamic content disabled.")
    GENERATOR_AVAILABLE = False

try:
    from .ip_flagger import flag_suspicious_ip # Assuming ip_flagger is in the same directory
    FLAGGING_AVAILABLE = True
except ImportError:
    print("Warning: Could not import ip_flagger. IP Flagging disabled.")
    def flag_suspicious_ip(ip: str): pass # Dummy function
    FLAGGING_AVAILABLE = False


# --- Configuration ---
ESCALATION_ENDPOINT = os.getenv("ESCALATION_ENDPOINT", "http://escalation_engine:8003/escalate")

app = FastAPI()

# --- Helper Functions ---
async def slow_stream_content(content: str, delay: float = 0.5):
    """Generator function to stream content slowly."""
    lines = content.split('\n')
    for line in lines:
        yield line + '\n'
        await asyncio.sleep(delay * random.uniform(0.5, 1.5))


# --- API Endpoints ---
@app.get("/tarpit", response_class=StreamingResponse)
@app.get("/tarpit/page/{page_name:path}", response_class=StreamingResponse)
@app.get("/tarpit/js/{script_name:path}", response_class=StreamingResponse)
async def tarpit_handler(request: Request, page_name: str = None, script_name: str = None):
    """
    Handles requests redirected here (potential honeypot triggers).
    Logs the hit, flags IP, escalates metadata, and serves a slow, fake response.
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    referer = request.headers.get("referer", "-")
    requested_path = str(request.url.path)
    http_method = request.method

    # Log the hit as a honeypot event
    print(f"TAR PIT HIT: Path={requested_path}, IP={client_ip}, UA='{user_agent}'") # Keep console log
    honeypot_details = {
        "ip": client_ip,
        "user_agent": user_agent,
        "method": http_method,
        "path": requested_path,
        "referer": referer,
        "headers": dict(request.headers) # Log headers for context
    }
    if HONEYPOT_LOGGING_AVAILABLE:
        log_honeypot_hit(honeypot_details) # Call the dedicated logger

    # --- IP Flagging ---
    if FLAGGING_AVAILABLE:
        try:
            flag_suspicious_ip(client_ip)
        except Exception as e:
            print(f"Error during IP flagging for {client_ip}: {e}")

    # --- Escalation ---
    metadata = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
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
            response.raise_for_status()
    except httpx.RequestError as exc:
        print(f"Error escalating request: {exc}")
    except Exception as e:
        print(f"Unexpected error during escalation: {e}")

    # --- Response Generation ---
    if GENERATOR_AVAILABLE:
        try:
            content = generate_dynamic_tarpit_page()
        except Exception as e:
            print(f"Error generating dynamic page: {e}")
            content = "<html><body>Service temporarily unavailable. Please try again later.</body></html>"
    else:
        content = """<!DOCTYPE html>
<html><head><title>Loading Resource...</title><meta name="robots" content="noindex, nofollow"></head>
<body><h1>Please wait</h1><p>Your content is loading...</p><progress></progress></body></html>"""

    # --- Stream the response slowly ---
    stream_delay = 0.8
    return StreamingResponse(slow_stream_content(content, delay=stream_delay), media_type="text/html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)