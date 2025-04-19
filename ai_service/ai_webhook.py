# ai_service/ai_webhook.py
# Receives webhook events, logs, blocklists via Redis, and sends configurable alerts.

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, Literal
import datetime
import pprint
import os
import redis # For blocklisting
import json
import httpx # For sending generic webhook alerts
import smtplib # For sending alerts via email
import ssl # For SMTP TLS/SSL
from email.mime.text import MIMEText # For sending alerts via email
import requests # Using requests for Slack webhook simplicity
import asyncio # For running sync code in thread pool

# --- Configuration ---

# Redis (Blocklist)
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB_BLOCKLIST = int(os.getenv("REDIS_DB_BLOCKLIST", 2)) # Use separate DB for blocklist
BLOCKLIST_KEY = "blocklist:ip" # Redis set key for storing blocked IPs

# Alerting Method & Config
ALERT_METHOD = os.getenv("ALERT_METHOD", "none").lower() # Options: "webhook", "slack", "smtp", "none"
ALERT_GENERIC_WEBHOOK_URL = os.getenv("ALERT_GENERIC_WEBHOOK_URL") # For 'webhook' method
ALERT_SLACK_WEBHOOK_URL = os.getenv("ALERT_SLACK_WEBHOOK_URL")   # For 'slack' method (Get from Slack App Incoming Webhooks)
ALERT_SMTP_HOST = os.getenv("ALERT_SMTP_HOST")                   # For 'smtp' method
ALERT_SMTP_PORT = int(os.getenv("ALERT_SMTP_PORT", 587))         # 587=TLS, 465=SSL, 25=None
ALERT_SMTP_USER = os.getenv("ALERT_SMTP_USER")                   # For 'smtp' method
ALERT_SMTP_PASSWORD = os.getenv("ALERT_SMTP_PASSWORD")           # For 'smtp' method (Use Docker secrets!)
ALERT_SMTP_PASSWORD_FILE = os.getenv("ALERT_SMTP_PASSWORD_FILE") # Optional: Path to Docker secret file
ALERT_SMTP_USE_TLS = os.getenv("ALERT_SMTP_USE_TLS", "true").lower() == "true" # Use TLS (like STARTTLS)
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", ALERT_SMTP_USER) # Default From address
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO")                     # Comma-separated for multiple recipients
ALERT_MIN_REASON_SEVERITY = os.getenv("ALERT_MIN_REASON_SEVERITY", "Local LLM") # e.g., "High Heuristic", "Local LLM", "External API"

# Logging Configuration
LOG_DIR = "/app/logs"
BLOCK_LOG_FILE = os.path.join(LOG_DIR, "block_events.log")
ALERT_LOG_FILE = os.path.join(LOG_DIR, "alert_events.log")
ERROR_LOG_FILE = os.path.join(LOG_DIR, "aiservice_errors.log")
os.makedirs(LOG_DIR, exist_ok=True) # Create log directory if needed

# --- Setup Clients & Load Secrets ---

# Redis Client
BLOCKLISTING_ENABLED = False
redis_client_blocklist = None
try:
    redis_pool_blocklist = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB_BLOCKLIST, decode_responses=True)
    redis_client_blocklist = redis.Redis(connection_pool=redis_pool_blocklist)
    redis_client_blocklist.ping()
    print(f"Connected to Redis for blocklisting at {REDIS_HOST}:{REDIS_PORT}, DB: {REDIS_DB_BLOCKLIST}")
    BLOCKLISTING_ENABLED = True
except redis.exceptions.ConnectionError as e:
    print(f"ERROR: Redis connection failed for Blocklisting: {e}. Blocklisting disabled.")
except Exception as e:
    print(f"ERROR: Unexpected error connecting to Redis for Blocklisting: {e}. Blocklisting disabled.")

# Load SMTP Password from secret file if path is provided
if ALERT_SMTP_PASSWORD_FILE and os.path.exists(ALERT_SMTP_PASSWORD_FILE):
    try:
        with open(ALERT_SMTP_PASSWORD_FILE, 'r') as f_secret:
            ALERT_SMTP_PASSWORD = f_secret.read().strip()
            print("Loaded SMTP password from secret file.")
    except Exception as e:
        print(f"ERROR: Failed to read SMTP password from secret file {ALERT_SMTP_PASSWORD_FILE}: {e}")
        # Fallback to environment variable if reading file fails but variable exists
        if not ALERT_SMTP_PASSWORD:
            ALERT_SMTP_PASSWORD = os.getenv("ALERT_SMTP_PASSWORD")
elif not ALERT_SMTP_PASSWORD:
     ALERT_SMTP_PASSWORD = os.getenv("ALERT_SMTP_PASSWORD") # Get from ENV if file not specified


# --- Pydantic Model ---
class WebhookEvent(BaseModel):
    event_type: str
    reason: str
    timestamp_utc: str | datetime.datetime
    details: Dict[str, Any]

# --- FastAPI App ---
app = FastAPI()

# --- Helper Functions ---

def log_error(message: str, exception: Exception = None):
    """Logs errors to a dedicated error log file."""
    try:
        timestamp = datetime.datetime.utcnow().isoformat() + "Z"
        log_entry = f"{timestamp} - ERROR: {message}"
        if exception: log_entry += f" | Exception: {type(exception).__name__}: {exception}"
        print(log_entry)
        # Append mode, create file if not exists
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f: f.write(log_entry + "\n")
    except Exception as log_e: print(f"FATAL: Could not write to error log file {ERROR_LOG_FILE}: {log_e}")

def log_event(log_file: str, event_type: str, data: dict):
    """Logs structured events to a specified file."""
    try:
        # Ensure details are serializable (convert datetime etc.)
        serializable_data = json.loads(json.dumps(data, default=str))
        log_entry = { "timestamp": datetime.datetime.utcnow().isoformat() + "Z", "event_type": event_type, **serializable_data }
        with open(log_file, "a", encoding="utf-8") as f: f.write(json.dumps(log_entry) + "\n")
    except Exception as e: log_error(f"Failed to write to log file {log_file}", e)

# --- Action Functions ---

def add_ip_to_blocklist(ip_address: str, reason: str, event_details: dict = None) -> bool:
    """Adds an IP address to the Redis blocklist set."""
    if not BLOCKLISTING_ENABLED or not ip_address or ip_address == "unknown":
        # print(f"Blocklisting disabled or IP invalid ('{ip_address}'), skipping block.") # Reduce noise
        return False
    try:
        added_count = redis_client_blocklist.sadd(BLOCKLIST_KEY, ip_address)
        if added_count > 0:
            print(f"Added IP {ip_address} to Redis blocklist set '{BLOCKLIST_KEY}'. Reason: {reason}")
            log_event(BLOCK_LOG_FILE, "BLOCKLIST_ADD", {"ip_address": ip_address, "reason": reason, "details": event_details})
            return True
        else: return True # Already present is considered success
    except redis.exceptions.RedisError as e: log_error(f"Redis error adding IP {ip_address} to blocklist", e); return False
    except Exception as e: log_error(f"Unexpected error adding IP {ip_address} to blocklist", e); return False

async def send_generic_webhook_alert(event_data: WebhookEvent):
    """Sends alert to a generic webhook URL using httpx."""
    if not ALERT_GENERIC_WEBHOOK_URL: return
    print(f"Sending generic webhook alert for IP: {event_data.details.get('ip')}")
    payload = { "alert_type": "AI_DEFENSE_BLOCK", "reason": event_data.reason, "timestamp": str(event_data.timestamp_utc), "ip_address": event_data.details.get('ip'), "user_agent": event_data.details.get('user_agent'), "details": event_data.details }
    try:
        async with httpx.AsyncClient() as client:
            # Ensure payload is serializable before sending
            response = await client.post(ALERT_GENERIC_WEBHOOK_URL, json=json.loads(json.dumps(payload, default=str)), timeout=10.0)
            response.raise_for_status()
            print(f"Generic webhook alert sent successfully.")
            log_event(ALERT_LOG_FILE, "ALERT_SENT_WEBHOOK", {"reason": event_data.reason, "ip": event_data.details.get('ip')})
    except Exception as e: log_error(f"Failed to send generic webhook alert to {ALERT_GENERIC_WEBHOOK_URL}", e)

async def send_slack_alert(event_data: WebhookEvent):
    """Sends alert to Slack via Incoming Webhook using requests."""
    if not ALERT_SLACK_WEBHOOK_URL: return
    print(f"Sending Slack alert for IP: {event_data.details.get('ip')}")
    ip = event_data.details.get('ip', 'N/A'); ua = event_data.details.get('user_agent', 'N/A'); reason = event_data.reason
    # Simple text format, can be enhanced with Slack blocks: https://api.slack.com/block-kit
    message = f":shield: *AI Defense Alert*\n> *Reason:* {reason}\n> *IP Address:* `{ip}`\n> *User Agent:* `{ua}`\n> *Timestamp:* {event_data.timestamp_utc}"
    payload = {"text": message}
    headers = {'Content-Type': 'application/json'}
    try:
        # Run synchronous requests call in thread pool to avoid blocking FastAPI
        response = await asyncio.to_thread(
            requests.post, ALERT_SLACK_WEBHOOK_URL, headers=headers, json=payload, timeout=10.0
        )
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        print(f"Slack alert sent successfully.")
        log_event(ALERT_LOG_FILE, "ALERT_SENT_SLACK", {"reason": event_data.reason, "ip": ip})
    except requests.exceptions.RequestException as e:
        log_error(f"Failed to send Slack alert using requests to {ALERT_SLACK_WEBHOOK_URL}", e)
    except Exception as e:
        log_error(f"Unexpected error sending Slack alert", e)

async def send_smtp_alert(event_data: WebhookEvent):
    """Sends alert via SMTP email using smtplib."""
    if not ALERT_EMAIL_TO or not ALERT_SMTP_HOST or not ALERT_EMAIL_FROM:
        log_error("SMTP alert configured but missing To, Host, or From address.")
        return
    print(f"Sending SMTP alert for IP: {event_data.details.get('ip')} to {ALERT_EMAIL_TO}")
    ip = event_data.details.get('ip', 'N/A'); ua = event_data.details.get('user_agent', 'N/A'); reason = event_data.reason
    subject = f"[AI Defense Alert] Suspicious Activity Detected - {reason}"
    body = f"""Suspicious activity detected by the AI Defense System:

Reason: {reason}
Timestamp: {event_data.timestamp_utc}
IP Address: {ip}
User Agent: {ua}

Full Details:
{pprint.pformat(event_data.details)}
"""
    msg = MIMEText(body, 'plain', 'utf-8') # Specify plain text and encoding
    msg['Subject'] = subject; msg['From'] = ALERT_EMAIL_FROM; msg['To'] = ALERT_EMAIL_TO

    # Function to run blocking SMTP code in thread pool
    def smtp_send_sync():
        smtp_conn = None
        try:
            if ALERT_SMTP_PORT == 465: # SSL Connection
                 context = ssl.create_default_context()
                 smtp_conn = smtplib.SMTP_SSL(ALERT_SMTP_HOST, ALERT_SMTP_PORT, timeout=15, context=context)
            else: # Plain (Port 25) or TLS (STARTTLS - Port 587 usually)
                 smtp_conn = smtplib.SMTP(ALERT_SMTP_HOST, ALERT_SMTP_PORT, timeout=15)
                 if ALERT_SMTP_USE_TLS: # Upgrade to TLS if configured (for port 587 mostly)
                    smtp_conn.starttls(context=ssl.create_default_context())

            if ALERT_SMTP_USER and ALERT_SMTP_PASSWORD: # Login if credentials provided
                smtp_conn.login(ALERT_SMTP_USER, ALERT_SMTP_PASSWORD)

            smtp_conn.sendmail(ALERT_EMAIL_FROM, ALERT_EMAIL_TO.split(','), msg.as_string())
            print(f"SMTP alert sent successfully to {ALERT_EMAIL_TO}.")
            # Log success after sendmail completes without error
            log_event(ALERT_LOG_FILE, "ALERT_SENT_SMTP", {"reason": reason, "ip": ip, "to": ALERT_EMAIL_TO})

        except smtplib.SMTPException as e: log_error(f"SMTP error sending email alert (Host: {ALERT_SMTP_HOST}:{ALERT_SMTP_PORT}, User: {ALERT_SMTP_USER})", e)
        except Exception as e: log_error(f"Unexpected error sending email alert", e)
        finally:
            if smtp_conn:
                try: smtp_conn.quit()
                except Exception: pass # Ignore errors during quit

    try:
        # Run the synchronous SMTP logic in a separate thread
        await asyncio.to_thread(smtp_send_sync)
    except Exception as e:
         log_error("Error executing SMTP send thread", e)


async def send_alert(event_data: WebhookEvent):
    """Dispatches alert based on configured ALERT_METHOD and severity."""
    # Simple severity check (customize as needed)
    severity_map = {"High Heuristic": 1, "Local LLM": 2, "External API": 3, "High Combined": 1} # Added High Combined
    reason_key = event_data.reason.split("(")[0].strip()
    event_severity = severity_map.get(reason_key, 0)
    min_severity_reason = ALERT_MIN_REASON_SEVERITY.split(" ")[0].strip()
    min_severity = severity_map.get(min_severity_reason, 1)

    if event_severity < min_severity: return # Severity check

    # Dispatch based on method
    print(f"Dispatching alert via method: {ALERT_METHOD}")
    if ALERT_METHOD == "webhook": await send_generic_webhook_alert(event_data)
    elif ALERT_METHOD == "slack": await send_slack_alert(event_data)
    elif ALERT_METHOD == "smtp": await send_smtp_alert(event_data)
    elif ALERT_METHOD != "none": log_error(f"Alert method '{ALERT_METHOD}' is invalid or missing configuration.")


# --- Webhook Receiver Endpoint ---
@app.post("/analyze")
async def receive_webhook(event: WebhookEvent, request: Request):
    """Receives webhook events, logs, blocklists, and sends alerts."""
    client_ip = request.client.host if request.client else "unknown" # IP sending webhook
    flagged_ip = event.details.get("ip", "unknown")
    print(f"Webhook Received from {client_ip} for flagged IP: {flagged_ip} - Reason: {event.reason}")

    action_taken = "logged"; blocklist_success = False

    # Blocklist the IP if reason indicates high confidence bot detection
    if any(term in event.reason for term in ["High Combined Score", "Local LLM Classification", "External API Classification", "High Heuristic Score", "Honeypot_Hit"]): # Added Honeypot
        if flagged_ip != "unknown":
            blocklist_success = add_ip_to_blocklist(flagged_ip, event.reason, event.details)
            action_taken = "ip_blocklisted" if blocklist_success else "blocklist_failed"
        else: action_taken = "blocklist_skipped_unknown_ip"
    else: print(f"Reason '{event.reason}' does not meet auto-block criteria.")

    # Send alert
    await send_alert(event)
    if ALERT_METHOD != "none": action_taken += "_alert_checked"

    print(f"Processing complete for IP {flagged_ip}. Action: {action_taken}")
    return {"status": "processed", "action_taken": action_taken, "ip_processed": flagged_ip}


if __name__ == "__main__":
    import uvicorn
    print(f"--- AI Service / Webhook Receiver Starting ---")
    print(f"Blocklisting via Redis: {'Enabled' if BLOCKLISTING_ENABLED else 'Disabled'} (Host: {REDIS_HOST}:{REDIS_PORT} DB:{REDIS_DB_BLOCKLIST})")
    print(f"Alert Method: {ALERT_METHOD}")
    if ALERT_METHOD == "webhook": print(f" -> Generic URL: {'Set' if ALERT_GENERIC_WEBHOOK_URL else 'Not Set'}")
    if ALERT_METHOD == "slack": print(f" -> Slack URL: {'Set' if ALERT_SLACK_WEBHOOK_URL else 'Not Set'}")
    if ALERT_METHOD == "smtp": print(f" -> SMTP Host: {ALERT_SMTP_HOST}:{ALERT_SMTP_PORT} | Use TLS: {ALERT_SMTP_USE_TLS} | From: {ALERT_EMAIL_FROM} | To: {ALERT_EMAIL_TO}")
    print(f"Logging blocks to: {BLOCK_LOG_FILE}")
    print(f"Logging alerts to: {ALERT_LOG_FILE}")
    print(f"Logging errors to: {ERROR_LOG_FILE}")
    print(f"-------------------------------------------")
    uvicorn.run(app, host="0.0.0.0", port=8000) # Port 8000 used in docker-compose example