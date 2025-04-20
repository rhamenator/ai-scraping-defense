# ai_service/ai_webhook.py
# Receives webhook events, logs, blocklists via Redis, and sends configurable alerts.

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, Field, ValidationError
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
import requests # Using requests for Slack webhook simplicity (sync call)
import asyncio # For running sync code in thread pool
import logging # Added for better logging

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---

# Redis (Blocklist)
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB_BLOCKLIST = int(os.getenv("REDIS_DB_BLOCKLIST", 2)) # Use separate DB for blocklist
BLOCKLIST_KEY = "blocklist:ip" # Redis set key for storing blocked IPs
# Optional: Add TTL for blocklist entries if desired (e.g., block for 24h)
# BLOCKLIST_TTL_SECONDS = int(os.getenv("BLOCKLIST_TTL_SECONDS", 86400)) # 0 means no TTL

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
    logger.info(f"Connected to Redis for blocklisting at {REDIS_HOST}:{REDIS_PORT}, DB: {REDIS_DB_BLOCKLIST}")
    BLOCKLISTING_ENABLED = True
except redis.exceptions.ConnectionError as e:
    logger.error(f"Redis connection failed for Blocklisting: {e}. Blocklisting disabled.")
except Exception as e:
    logger.error(f"Unexpected error connecting to Redis for Blocklisting: {e}. Blocklisting disabled.")

# Load SMTP Password from secret file if path is provided
smtp_password_loaded = False
if ALERT_SMTP_PASSWORD_FILE and os.path.exists(ALERT_SMTP_PASSWORD_FILE):
    try:
        with open(ALERT_SMTP_PASSWORD_FILE, 'r') as f_secret:
            ALERT_SMTP_PASSWORD = f_secret.read().strip()
            logger.info("Loaded SMTP password from secret file.")
            smtp_password_loaded = True
    except Exception as e:
        logger.error(f"Failed to read SMTP password from secret file {ALERT_SMTP_PASSWORD_FILE}: {e}")
        # Fallback to environment variable if reading file fails but variable exists
        if not ALERT_SMTP_PASSWORD:
            ALERT_SMTP_PASSWORD = os.getenv("ALERT_SMTP_PASSWORD")
            if ALERT_SMTP_PASSWORD: smtp_password_loaded = True
elif not ALERT_SMTP_PASSWORD:
     ALERT_SMTP_PASSWORD = os.getenv("ALERT_SMTP_PASSWORD") # Get from ENV if file not specified
     if ALERT_SMTP_PASSWORD: smtp_password_loaded = True

if ALERT_METHOD == "smtp" and not smtp_password_loaded and ALERT_SMTP_USER:
     logger.warning("SMTP alerting configured but SMTP password is not set (via ENV or secret file). Authentication may fail.")


# --- Pydantic Model ---
class WebhookEvent(BaseModel):
    event_type: str = Field(..., description="Type of event, e.g., 'suspicious_activity_detected'")
    reason: str = Field(..., description="Reason for the event/block, e.g., 'High Combined Score (0.95)'")
    timestamp_utc: str | datetime.datetime = Field(..., description="Timestamp of the original detection")
    details: Dict[str, Any] = Field(..., description="Detailed metadata about the request (IP, UA, headers, etc.)")

# --- FastAPI App ---
app = FastAPI(
    title="AI Defense Webhook Service",
    description="Receives analysis results, manages blocklists, and sends alerts."
)

# --- Helper Functions ---

def log_error(message: str, exception: Exception = None):
    """Logs errors to a dedicated error log file and standard logger."""
    try:
        timestamp = datetime.datetime.utcnow().isoformat() + "Z"
        log_entry = f"{timestamp} - ERROR: {message}"
        if exception: log_entry += f" | Exception: {type(exception).__name__}: {exception}"
        logger.error(log_entry) # Use standard logger
        # Append mode, create file if not exists
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f: f.write(log_entry + "\n")
    except Exception as log_e:
        # Log to stderr as last resort
        print(f"FATAL: Could not write to error log file {ERROR_LOG_FILE}: {log_e}")
        print(f"Original error: {log_entry}")

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
        if ip_address == "unknown": logger.warning(f"Attempted to blocklist 'unknown' IP. Reason: {reason}. Details: {event_details}")
        return False
    try:
        added_count = redis_client_blocklist.sadd(BLOCKLIST_KEY, ip_address)
        # Optional: Set TTL if configured
        # if BLOCKLIST_TTL_SECONDS > 0:
        #     redis_client_blocklist.expire(BLOCKLIST_KEY, BLOCKLIST_TTL_SECONDS) # Note: This sets TTL on the SET key, not individual members

        if added_count > 0:
            logger.info(f"Added IP {ip_address} to Redis blocklist set '{BLOCKLIST_KEY}'. Reason: {reason}")
            log_event(BLOCK_LOG_FILE, "BLOCKLIST_ADD", {"ip_address": ip_address, "reason": reason, "details": event_details})
            return True
        else:
            # logger.debug(f"IP {ip_address} already present in blocklist '{BLOCKLIST_KEY}'.")
            return True # Already present is considered success
    except redis.exceptions.RedisError as e: log_error(f"Redis error adding IP {ip_address} to blocklist", e); return False
    except Exception as e: log_error(f"Unexpected error adding IP {ip_address} to blocklist", e); return False

async def send_generic_webhook_alert(event_data: WebhookEvent):
    """Sends alert to a generic webhook URL using httpx."""
    if not ALERT_GENERIC_WEBHOOK_URL: return
    ip = event_data.details.get('ip', 'N/A')
    logger.info(f"Sending generic webhook alert for IP: {ip}")
    payload = { "alert_type": "AI_DEFENSE_BLOCK", "reason": event_data.reason, "timestamp": str(event_data.timestamp_utc), "ip_address": ip, "user_agent": event_data.details.get('user_agent', 'N/A'), "details": event_data.details }
    try:
        # Ensure payload is serializable before sending
        json_payload = json.loads(json.dumps(payload, default=str))
        async with httpx.AsyncClient() as client:
            response = await client.post(ALERT_GENERIC_WEBHOOK_URL, json=json_payload, timeout=10.0)
            response.raise_for_status()
            logger.info(f"Generic webhook alert sent successfully for IP {ip}.")
            log_event(ALERT_LOG_FILE, "ALERT_SENT_WEBHOOK", {"reason": event_data.reason, "ip": ip})
    except json.JSONDecodeError as e: log_error(f"Failed to serialize generic webhook payload for IP {ip}", e)
    except httpx.RequestError as e: log_error(f"Failed to send generic webhook alert to {ALERT_GENERIC_WEBHOOK_URL} for IP {ip}", e)
    except httpx.HTTPStatusError as e: log_error(f"Generic webhook alert failed for IP {ip} with status {e.response.status_code}", e)
    except Exception as e: log_error(f"Unexpected error sending generic webhook alert for IP {ip}", e)

async def send_slack_alert(event_data: WebhookEvent):
    """Sends alert to Slack via Incoming Webhook using requests (sync in thread pool)."""
    if not ALERT_SLACK_WEBHOOK_URL: return
    ip = event_data.details.get('ip', 'N/A'); ua = event_data.details.get('user_agent', 'N/A'); reason = event_data.reason
    logger.info(f"Sending Slack alert for IP: {ip}")

    # Simple text format, can be enhanced with Slack blocks: https://api.slack.com/block-kit
    message = f":shield: *AI Defense Alert*\n> *Reason:* {reason}\n> *IP Address:* `{ip}`\n> *User Agent:* `{ua}`\n> *Timestamp (UTC):* {event_data.timestamp_utc}"
    payload = {"text": message}
    headers = {'Content-Type': 'application/json'}
    try:
        # Run synchronous requests call in thread pool to avoid blocking FastAPI
        response = await asyncio.to_thread(
            requests.post, ALERT_SLACK_WEBHOOK_URL, headers=headers, json=payload, timeout=10.0
        )
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        logger.info(f"Slack alert sent successfully for IP {ip}.")
        log_event(ALERT_LOG_FILE, "ALERT_SENT_SLACK", {"reason": reason, "ip": ip})
    except requests.exceptions.RequestException as e:
        log_error(f"Failed to send Slack alert using requests to {ALERT_SLACK_WEBHOOK_URL} for IP {ip}", e)
    except Exception as e:
        log_error(f"Unexpected error sending Slack alert for IP {ip}", e)

async def send_smtp_alert(event_data: WebhookEvent):
    """Sends alert via SMTP email using smtplib (sync in thread pool)."""
    if not ALERT_EMAIL_TO or not ALERT_SMTP_HOST or not ALERT_EMAIL_FROM:
        log_error("SMTP alert configured but missing To, Host, or From address.")
        return
    ip = event_data.details.get('ip', 'N/A'); ua = event_data.details.get('user_agent', 'N/A'); reason = event_data.reason
    logger.info(f"Sending SMTP alert for IP: {ip} to {ALERT_EMAIL_TO}")

    subject = f"[AI Defense Alert] Suspicious Activity Detected - {reason}"
    body = f"""Suspicious activity detected by the AI Defense System:

Reason: {reason}
Timestamp (UTC): {event_data.timestamp_utc}
IP Address: {ip}
User Agent: {ua}

Full Details:
{pprint.pformat(event_data.details)}

---
Consider integrating this IP with Fail2ban or firewall rules if recurring.
Check logs in {LOG_DIR} for more context.
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
                    context = ssl.create_default_context()
                    smtp_conn.starttls(context=context)

            if ALERT_SMTP_USER and ALERT_SMTP_PASSWORD: # Login if credentials provided
                smtp_conn.login(ALERT_SMTP_USER, ALERT_SMTP_PASSWORD)
            else:
                logger.warning("SMTP User/Password not provided for login.")

            smtp_conn.sendmail(ALERT_EMAIL_FROM, ALERT_EMAIL_TO.split(','), msg.as_string())
            logger.info(f"SMTP alert sent successfully for IP {ip} to {ALERT_EMAIL_TO}.")
            # Log success after sendmail completes without error
            log_event(ALERT_LOG_FILE, "ALERT_SENT_SMTP", {"reason": reason, "ip": ip, "to": ALERT_EMAIL_TO})

        except smtplib.SMTPException as e: log_error(f"SMTP error sending email alert for IP {ip} (Host: {ALERT_SMTP_HOST}:{ALERT_SMTP_PORT}, User: {ALERT_SMTP_USER})", e)
        except Exception as e: log_error(f"Unexpected error sending email alert for IP {ip}", e)
        finally:
            if smtp_conn:
                try: smtp_conn.quit()
                except Exception: pass # Ignore errors during quit

    try:
        # Run the synchronous SMTP logic in a separate thread
        await asyncio.to_thread(smtp_send_sync)
    except Exception as e:
         log_error(f"Error executing SMTP send thread for IP {ip}", e)


async def send_alert(event_data: WebhookEvent):
    """Dispatches alert based on configured ALERT_METHOD and severity."""
    # Simple severity mapping (can be customized)
    severity_map = {"High Heuristic": 1, "Local LLM": 2, "External API": 3, "High Combined": 1, "Honeypot_Hit": 2} # Added Honeypot
    # Extract base reason for mapping
    reason_key = event_data.reason.split("(")[0].strip()
    event_severity = severity_map.get(reason_key, 0) # Default severity 0 if reason not mapped

    # Map minimum severity reason from config
    min_severity_reason = ALERT_MIN_REASON_SEVERITY.split(" ")[0].strip()
    min_severity = severity_map.get(min_severity_reason, 1) # Default min severity 1

    if event_severity < min_severity:
        logger.debug(f"Skipping alert for IP {event_data.details.get('ip')}. Severity {event_severity} ('{reason_key}') < Min Severity {min_severity} ('{min_severity_reason}')")
        return # Severity check failed

    # Dispatch based on method
    logger.info(f"Dispatching alert for IP {event_data.details.get('ip')} via method: {ALERT_METHOD} (Severity: {event_severity})")
    if ALERT_METHOD == "webhook": await send_generic_webhook_alert(event_data)
    elif ALERT_METHOD == "slack": await send_slack_alert(event_data)
    elif ALERT_METHOD == "smtp": await send_smtp_alert(event_data)
    elif ALERT_METHOD == "none": pass # Explicitly do nothing
    else: log_error(f"Alert method '{ALERT_METHOD}' is invalid or missing configuration.")


# --- Webhook Receiver Endpoint ---
@app.post("/analyze", status_code=202) # Use 202 Accepted as processing happens async
async def receive_webhook(event: WebhookEvent, request: Request):
    """
    Receives webhook events, logs, blocklists (if applicable), and triggers alerts.
    """
    client_ip = request.client.host if request.client else "unknown" # IP sending webhook
    flagged_ip = event.details.get("ip", "unknown")
    reason = event.reason or "Unknown Reason"
    logger.info(f"Webhook Received from {client_ip} for flagged IP: {flagged_ip} - Reason: {reason}")

    # Validate payload basics
    if flagged_ip == "unknown":
         logger.warning(f"Webhook received with 'unknown' IP address from {client_ip}. Reason: {reason}")
         # Decide if we should still process alerts etc. maybe based on reason?
         # For now, let's return an error if IP is missing/unknown
         # raise HTTPException(status_code=400, detail="Missing or 'unknown' IP address in webhook details")
         # Or just log and proceed cautiously:
         pass # Continue processing but blocklisting will fail

    action_taken = "logged"; blocklist_success = False

    # Auto-Blocklist Criteria (Adjust terms as needed based on Escalation Engine reasons)
    # Note: Ensure reasons sent by Escalation Engine match these terms.
    auto_block_reasons = ["High Combined Score", "Local LLM Classification", "External API Classification", "High Heuristic Score", "Honeypot_Hit"]

    if any(term in reason for term in auto_block_reasons):
        if flagged_ip != "unknown":
            blocklist_success = add_ip_to_blocklist(flagged_ip, reason, event.details)
            action_taken = "ip_blocklisted" if blocklist_success else "blocklist_failed"
        else:
            action_taken = "blocklist_skipped_unknown_ip"
            logger.warning(f"Cannot blocklist 'unknown' IP for reason: {reason}")
    else:
        logger.info(f"Reason '{reason}' for IP {flagged_ip} does not meet auto-block criteria. Skipping blocklist.")
        action_taken = "blocklist_skipped_criteria_not_met"

    # Send alert (runs checks internally)
    try:
        await send_alert(event)
        if ALERT_METHOD != "none": action_taken += "_alert_checked"
    except Exception as e:
        log_error(f"Error during alert processing for IP {flagged_ip}", e)
        action_taken += "_alert_error"

    logger.info(f"Processing complete for IP {flagged_ip}. Action: {action_taken}")
    return {"status": "processed", "action_taken": action_taken, "ip_processed": flagged_ip}


# --- Health Check Endpoint ---
@app.get("/health")
async def health_check():
    """ Basic health check endpoint """
    # Check Redis connection?
    redis_ok = False
    if redis_client_blocklist:
        try:
            redis_ok = redis_client_blocklist.ping()
        except Exception:
            redis_ok = False
    return {"status": "ok", "redis_blocklist_connected": redis_ok}


if __name__ == "__main__":
    import uvicorn
    logger.info("--- AI Service / Webhook Receiver Starting ---")
    logger.info(f"Blocklisting via Redis: {'Enabled' if BLOCKLISTING_ENABLED else 'Disabled'} (Host: {REDIS_HOST}:{REDIS_PORT} DB:{REDIS_DB_BLOCKLIST})")
    logger.info(f"Alert Method: {ALERT_METHOD}")
    if ALERT_METHOD == "webhook": logger.info(f" -> Generic URL: {'Set' if ALERT_GENERIC_WEBHOOK_URL else 'Not Set'}")
    if ALERT_METHOD == "slack": logger.info(f" -> Slack URL: {'Set' if ALERT_SLACK_WEBHOOK_URL else 'Not Set'}")
    if ALERT_METHOD == "smtp": logger.info(f" -> SMTP Host: {ALERT_SMTP_HOST}:{ALERT_SMTP_PORT} | Use TLS: {ALERT_SMTP_USE_TLS} | From: {ALERT_EMAIL_FROM} | To: {ALERT_EMAIL_TO} | Pass Loaded: {smtp_password_loaded}")
    logger.info(f"Minimum Alert Severity Reason: {ALERT_MIN_REASON_SEVERITY}")
    logger.info(f"Logging blocks to: {BLOCK_LOG_FILE}")
    logger.info(f"Logging alerts to: {ALERT_LOG_FILE}")
    logger.info(f"Logging errors to: {ERROR_LOG_FILE}")
    logger.info("Recommendation: Integrate block events with Fail2ban/CrowdSec or firewall rules for automated blocking.")
    logger.info("-------------------------------------------")
    # Use reload=True only for development
    uvicorn.run(app, host="0.0.0.0", port=8000)