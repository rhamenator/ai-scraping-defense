# ai_service/ai_webhook.py
# Receives webhook events, logs, blocklists via Redis (with TTL), optionally reports to community lists, and sends alerts.

from flask import Flask, jsonify, request
from pydantic import BaseModel, Field, ValidationError
from typing import Dict, Any, Literal, Optional, Union
import datetime
import pprint
import os
import redis
from redis.exceptions import ConnectionError, RedisError
from src.shared.config import get_secret
from src.shared.redis_client import get_redis_connection as shared_get_redis_connection
import json
import httpx 
import smtplib 
import ssl 
from email.mime.text import MIMEText 
import requests 
import asyncio 
import logging

# --- Updated Metrics Import ---
try:
    from shared.metrics import (
        increment_counter_metric, # Use the helper for counters
        COMMUNITY_REPORTS_ATTEMPTED,
        COMMUNITY_REPORTS_SUCCESS,
        COMMUNITY_REPORTS_ERRORS_TIMEOUT,
        COMMUNITY_REPORTS_ERRORS_REQUEST,
        COMMUNITY_REPORTS_ERRORS_STATUS,
        COMMUNITY_REPORTS_ERRORS_RESPONSE_DECODE,
        COMMUNITY_REPORTS_ERRORS_UNEXPECTED
        # Add other specific metrics if ai_webhook needs to increment them directly
    )
    METRICS_SYSTEM_AVAILABLE = True
    logging.info("Metrics system (prometheus client style) imported successfully by AI Webhook.")
except ImportError:
    logging.warning("Could not import specific metrics or helper from metrics.py. Metric incrementation will be no-op.")
    # Define dummy functions/objects if metrics are unavailable to prevent runtime errors
    def increment_counter_metric(metric_instance, labels=None): pass
    class DummyCounter:
        def inc(self, amount=1): pass
    COMMUNITY_REPORTS_ATTEMPTED = DummyCounter()
    COMMUNITY_REPORTS_SUCCESS = DummyCounter()
    COMMUNITY_REPORTS_ERRORS_TIMEOUT = DummyCounter()
    COMMUNITY_REPORTS_ERRORS_REQUEST = DummyCounter()
    COMMUNITY_REPORTS_ERRORS_STATUS = DummyCounter()
    COMMUNITY_REPORTS_ERRORS_RESPONSE_DECODE = DummyCounter()
    COMMUNITY_REPORTS_ERRORS_UNEXPECTED = DummyCounter()
    METRICS_SYSTEM_AVAILABLE = False

# --- Setup Logging ---
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') # Already set up by FastAPI/Uvicorn usually
logger = logging.getLogger(__name__) # Use __name__ for module-specific logger

# --- Configuration (remains the same) ---
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB_BLOCKLIST = int(os.getenv("REDIS_DB_BLOCKLIST", 2))
BLOCKLIST_KEY_PREFIX = "blocklist:ip:"
BLOCKLIST_TTL_SECONDS = int(os.getenv("BLOCKLIST_TTL_SECONDS", 86400))

ALERT_METHOD = os.getenv("ALERT_METHOD", "none").lower()
ALERT_GENERIC_WEBHOOK_URL = os.getenv("ALERT_GENERIC_WEBHOOK_URL")
ALERT_SLACK_WEBHOOK_URL = os.getenv("ALERT_SLACK_WEBHOOK_URL")
ALERT_SMTP_HOST = os.getenv("ALERT_SMTP_HOST", "mailhog")
ALERT_SMTP_PORT = int(os.getenv("ALERT_SMTP_PORT", 587))
ALERT_SMTP_USER = os.getenv("ALERT_SMTP_USER")
ALERT_SMTP_PASSWORD_FILE = os.getenv("ALERT_SMTP_PASSWORD_FILE", "/run/secrets/smtp_password")
ALERT_SMTP_PASSWORD = None  # Populated below
ALERT_SMTP_USE_TLS = os.getenv("ALERT_SMTP_USE_TLS", "true").lower() == "true"
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", ALERT_SMTP_USER)
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO")
ALERT_MIN_REASON_SEVERITY = os.getenv("ALERT_MIN_REASON_SEVERITY", "Local LLM")

ENABLE_COMMUNITY_REPORTING = os.getenv("ENABLE_COMMUNITY_REPORTING", "false").lower() == "true"
COMMUNITY_BLOCKLIST_REPORT_URL = os.getenv("COMMUNITY_BLOCKLIST_REPORT_URL")
COMMUNITY_BLOCKLIST_API_KEY_FILE = os.getenv("COMMUNITY_BLOCKLIST_API_KEY_FILE", "/run/secrets/community_blocklist_api_key")
COMMUNITY_BLOCKLIST_REPORT_TIMEOUT = float(os.getenv("COMMUNITY_BLOCKLIST_REPORT_TIMEOUT", 10.0))
COMMUNITY_BLOCKLIST_API_KEY = None  # Populated below

LOG_DIR = "/app/logs"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
BLOCK_LOG_FILE = os.path.join(LOG_DIR, "block_events.log")
ALERT_LOG_FILE = os.path.join(LOG_DIR, "alert_events.log")
ERROR_LOG_FILE = os.path.join(LOG_DIR, "aiservice_errors.log")
COMMUNITY_REPORT_LOG_FILE = os.path.join(LOG_DIR, "community_report.log")
os.makedirs(LOG_DIR, exist_ok=True)
WEBHOOK_API_KEY = os.getenv("WEBHOOK_API_KEY")

# --- Load Secrets ---
ALERT_SMTP_PASSWORD = get_secret("ALERT_SMTP_PASSWORD_FILE")
COMMUNITY_BLOCKLIST_API_KEY = get_secret("COMMUNITY_BLOCKLIST_API_KEY_FILE")

# --- Setup Clients & Validate Config ---
BLOCKLISTING_ENABLED = False
redis_client_blocklist = None
try:
    redis_client_blocklist = shared_get_redis_connection(db_number=REDIS_DB_BLOCKLIST)
    if redis_client_blocklist:
        redis_client_blocklist.ping()
        BLOCKLISTING_ENABLED = True
        logger.info(
            f"Connected to Redis for blocklisting at {REDIS_HOST}:{REDIS_PORT}, DB: {REDIS_DB_BLOCKLIST}"
        )
    else:
        logger.error("Redis connection for blocklisting returned None. Blocklisting disabled.")
except ConnectionError as e:
    logger.error(f"Redis connection failed for Blocklisting: {e}. Blocklisting disabled.")
except Exception as e:
    logger.error(f"Unexpected error connecting to Redis for Blocklisting: {e}. Blocklisting disabled.")

if ALERT_METHOD == "smtp" and not ALERT_SMTP_PASSWORD and ALERT_SMTP_USER:
     logger.warning("SMTP alerting configured but SMTP password is not set.")
if ENABLE_COMMUNITY_REPORTING and not COMMUNITY_BLOCKLIST_REPORT_URL:
    logger.warning("Community reporting enabled but COMMUNITY_BLOCKLIST_REPORT_URL is not set.")
if ENABLE_COMMUNITY_REPORTING and not COMMUNITY_BLOCKLIST_API_KEY:
    logger.warning("Community reporting enabled but COMMUNITY_BLOCKLIST_API_KEY secret could not be loaded.")

# --- Pydantic Model ---
class WebhookEvent(BaseModel):
    event_type: str = Field(..., description="Type of event, e.g., 'suspicious_activity_detected'")
    reason: str = Field(..., description="Reason for the event/block, e.g., 'High Combined Score (0.95)'")
    timestamp_utc: Union[str, datetime.datetime] = Field(..., description="Timestamp of the original detection") # Allow str or datetime
    details: Dict[str, Any] = Field(..., description="Detailed metadata about the request (IP, UA, headers, etc.)")

# --- Flask App ---
app = Flask(__name__)
app.config["TESTING"] = False


def get_redis_connection():
    """Wrapper for tests to patch the Redis client."""
    return redis_client_blocklist

# --- Helper Functions ---
def log_error(message: str, exception: Optional[Exception] = None):
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    log_entry = f"{timestamp} - ERROR: {message}"
    if exception: log_entry += f" | Exception: {type(exception).__name__}: {exception}"
    logger.error(log_entry)
    try:
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f: f.write(log_entry + "\n")
    except Exception as log_e: print(f"FATAL: Could not write to error log file {ERROR_LOG_FILE}: {log_e}\nOriginal error: {log_entry}")

def log_event(log_file: str, event_type: str, data: dict):
    try:
        serializable_data = json.loads(json.dumps(data, default=str))
        log_entry = { "timestamp": datetime.datetime.utcnow().isoformat() + "Z", "event_type": event_type, **serializable_data }
        with open(log_file, "a", encoding="utf-8") as f: f.write(json.dumps(log_entry) + "\n")
    except Exception as e: log_error(f"Failed to write to log file {log_file}", e)

# --- Action Functions ---
def add_ip_to_blocklist(ip_address: str, reason: str, event_details: Optional[dict] = None) -> bool:
    if not BLOCKLISTING_ENABLED or not redis_client_blocklist or not ip_address or ip_address == "unknown":
        if ip_address == "unknown": logger.warning(f"Attempted to blocklist 'unknown' IP. Reason: {reason}. Details: {event_details}")
        return False
    try:
        block_key = f"{BLOCKLIST_KEY_PREFIX}{ip_address}"
        block_metadata = json.dumps({ "reason": reason, "timestamp_utc": datetime.datetime.utcnow().isoformat() + "Z", "user_agent": event_details.get('user_agent', 'N/A') if event_details else 'N/A' })
        if redis_client_blocklist.exists(block_key):
            logger.info(f"IP {ip_address} already in blocklist. TTL refreshed")
        redis_client_blocklist.setex(block_key, BLOCKLIST_TTL_SECONDS, block_metadata)
        logger.info(f"Added/Refreshed IP {ip_address} to Redis blocklist (Key: {block_key}) with TTL {BLOCKLIST_TTL_SECONDS}s. Reason: {reason}")
        log_event(BLOCK_LOG_FILE, "BLOCKLIST_ADD_TTL", { "ip_address": ip_address, "reason": reason, "ttl_seconds": BLOCKLIST_TTL_SECONDS, "details": event_details })
        return True
    except RedisError as e: log_error(f"Redis error setting blocklist key for IP {ip_address}", e); return False
    except Exception as e: log_error(f"Unexpected error setting blocklist key for IP {ip_address}", e); return False

async def report_ip_to_community(ip: str, reason: str, details: dict) -> bool:
    if not ENABLE_COMMUNITY_REPORTING or not COMMUNITY_BLOCKLIST_REPORT_URL or not COMMUNITY_BLOCKLIST_API_KEY or not ip:
        if ENABLE_COMMUNITY_REPORTING and ip: logger.debug(f"Community reporting skipped for IP {ip}: URL or API Key not configured.")
        return False
    
    increment_counter_metric(COMMUNITY_REPORTS_ATTEMPTED) # Use new metric object
    logger.info(f"Reporting IP {ip} to community blocklist: {COMMUNITY_BLOCKLIST_REPORT_URL}")
    headers = { 'Accept': 'application/json', 'Key': COMMUNITY_BLOCKLIST_API_KEY }
    categories = "18"; # Default: Brute-Force
    if "scan" in reason.lower(): categories = "14"
    if "scraping" in reason.lower() or "crawler" in reason.lower() or "llm" in reason.lower(): categories = "19"
    if "honeypot" in reason.lower(): categories = "22"
    payload = { 'ip': ip, 'categories': categories, 'comment': f"AI Defense Stack Detection. Reason: {reason}. UA: {details.get('user_agent', 'N/A')}. Path: {details.get('path', 'N/A')}"[:1024] }
    response = None
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(COMMUNITY_BLOCKLIST_REPORT_URL, headers=headers, data=payload, timeout=COMMUNITY_BLOCKLIST_REPORT_TIMEOUT)
            response.raise_for_status()
            result = response.json()
            logger.info(f"Successfully reported IP {ip} to community blocklist. Response: {result}")
            log_event(COMMUNITY_REPORT_LOG_FILE, "COMMUNITY_REPORT_SUCCESS", {"ip": ip, "reason": reason, "api_response": result})
            increment_counter_metric(COMMUNITY_REPORTS_SUCCESS) # Use new metric object
            return True
    except httpx.TimeoutException: logger.error(f"Timeout reporting IP {ip}"); increment_counter_metric(COMMUNITY_REPORTS_ERRORS_TIMEOUT); return False
    except httpx.RequestError as exc: logger.error(f"Request error reporting IP {ip}: {exc}"); increment_counter_metric(COMMUNITY_REPORTS_ERRORS_REQUEST); return False
    except httpx.HTTPStatusError as exc: logger.error(f"Community blocklist report failed for IP {ip} status {exc.response.status_code}. Response: {exc.response.text[:500]}"); increment_counter_metric(COMMUNITY_REPORTS_ERRORS_STATUS); return False
    except json.JSONDecodeError as exc: logger.error(f"JSON decode error for IP {ip}: {exc} - Response: {(response.text[:500] if response else 'No response')}"); increment_counter_metric(COMMUNITY_REPORTS_ERRORS_RESPONSE_DECODE); return False
    except Exception as e: logger.error(f"Unexpected error reporting IP {ip}: {e}", exc_info=True); increment_counter_metric(COMMUNITY_REPORTS_ERRORS_UNEXPECTED); return False

# --- Alerting Functions (send_generic_webhook_alert, send_slack_alert, send_smtp_alert, send_alert) ---
# These functions remain largely the same, no direct metric calls in them.
async def send_generic_webhook_alert(event_data: WebhookEvent):
    if not ALERT_GENERIC_WEBHOOK_URL: return
    ip = event_data.details.get('ip', 'N/A')
    logger.info(f"Sending generic webhook alert for IP: {ip}")
    payload = { "alert_type": "AI_DEFENSE_BLOCK", "reason": event_data.reason, "timestamp": str(event_data.timestamp_utc), "ip_address": ip, "user_agent": event_data.details.get('user_agent', 'N/A'), "details": event_data.details }
    try:
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
    if not ALERT_SLACK_WEBHOOK_URL: return
    ip = event_data.details.get('ip', 'N/A'); ua = event_data.details.get('user_agent', 'N/A'); reason = event_data.reason
    logger.info(f"Sending Slack alert for IP: {ip}")
    message = f":shield: *AI Defense Alert*\n> *Reason:* {reason}\n> *IP Address:* `{ip}`\n> *User Agent:* `{ua}`\n> *Timestamp (UTC):* {event_data.timestamp_utc}"
    payload = {"text": message}; headers = {'Content-Type': 'application/json'}
    try:
        response = await asyncio.to_thread(requests.post, ALERT_SLACK_WEBHOOK_URL, headers=headers, json=payload, timeout=10.0)
        response.raise_for_status()
        logger.info(f"Slack alert sent successfully for IP {ip}.")
        log_event(ALERT_LOG_FILE, "ALERT_SENT_SLACK", {"reason": reason, "ip": ip})
    except requests.exceptions.RequestException as e: log_error(f"Failed to send Slack alert to {ALERT_SLACK_WEBHOOK_URL} for IP {ip}", e)
    except Exception as e: log_error(f"Unexpected error sending Slack alert for IP {ip}", e)

async def send_smtp_alert(event_data: WebhookEvent):
    if not ALERT_EMAIL_TO or not ALERT_SMTP_HOST or not ALERT_EMAIL_FROM: log_error("SMTP alert config missing."); return
    ip = event_data.details.get('ip', 'N/A'); ua = event_data.details.get('user_agent', 'N/A'); reason = event_data.reason
    logger.info(f"Sending SMTP alert for IP: {ip} to {ALERT_EMAIL_TO}")
    subject = f"[AI Defense Alert] Suspicious Activity Detected - {reason}"
    body = f"""Suspicious activity detected:
Reason: {reason}
Timestamp (UTC): {event_data.timestamp_utc}
IP Address: {ip}
User Agent: {ua}
Details: {pprint.pformat(event_data.details)}
---
IP added to blocklist (TTL: {BLOCKLIST_TTL_SECONDS}s). Logs in {LOG_DIR}.
"""
    msg = MIMEText(body, 'plain', 'utf-8'); msg['Subject'] = subject; msg['From'] = ALERT_EMAIL_FROM; msg['To'] = ALERT_EMAIL_TO
    def smtp_send_sync():
        smtp_conn = None
        try:
            if not ALERT_SMTP_HOST: logger.error("SMTP host not set."); return
            if ALERT_SMTP_PORT == 465: smtp_conn = smtplib.SMTP_SSL(str(ALERT_SMTP_HOST), ALERT_SMTP_PORT, timeout=15, context=ssl.create_default_context())
            else: smtp_conn = smtplib.SMTP(str(ALERT_SMTP_HOST), ALERT_SMTP_PORT, timeout=15)
            if ALERT_SMTP_USE_TLS and ALERT_SMTP_PORT != 465 : smtp_conn.starttls(context=ssl.create_default_context()) # Don't call starttls if already SSL
            if ALERT_SMTP_USER and ALERT_SMTP_PASSWORD: smtp_conn.login(ALERT_SMTP_USER, ALERT_SMTP_PASSWORD)
            elif ALERT_SMTP_USER: logger.warning("SMTP User provided but password missing.")
            from_addr = ALERT_EMAIL_FROM if ALERT_EMAIL_FROM else ""
            to_addrs = ALERT_EMAIL_TO.split(',') if ALERT_EMAIL_TO else []
            smtp_conn.sendmail(from_addr, to_addrs, msg.as_string())
            logger.info(f"SMTP alert sent for IP {ip} to {ALERT_EMAIL_TO}.")
            log_event(ALERT_LOG_FILE, "ALERT_SENT_SMTP", {"reason": reason, "ip": ip, "to": ALERT_EMAIL_TO})
        except smtplib.SMTPException as e: log_error(f"SMTP error for IP {ip} (Host: {ALERT_SMTP_HOST})", e)
        except Exception as e: log_error(f"Unexpected SMTP error for IP {ip}", e)
        finally:
            if smtp_conn:
                try: smtp_conn.quit()
                except Exception: pass
    try: await asyncio.to_thread(smtp_send_sync)
    except Exception as e: log_error(f"Error executing SMTP send thread for IP {ip}", e)

async def send_alert(event_data: WebhookEvent):
    severity_map = {"High Heuristic": 1, "Local LLM": 2, "External API": 3, "High Combined": 1, "Honeypot_Hit": 2, "IP Reputation": 1}
    reason_key = event_data.reason.split("(")[0].strip(); event_severity = severity_map.get(reason_key, 0)
    min_severity_reason = ALERT_MIN_REASON_SEVERITY.split(" ")[0].strip(); min_severity = severity_map.get(min_severity_reason, 1)
    if event_severity < min_severity: logger.debug(f"Skipping alert for IP {event_data.details.get('ip')}. Severity {event_severity} < Min {min_severity}"); return
    logger.info(f"Dispatching alert for IP {event_data.details.get('ip')} via method: {ALERT_METHOD} (Severity: {event_severity})")
    if ALERT_METHOD == "webhook": await send_generic_webhook_alert(event_data)
    elif ALERT_METHOD == "slack": await send_slack_alert(event_data)
    elif ALERT_METHOD == "smtp": await send_smtp_alert(event_data)
    elif ALERT_METHOD != "none": log_error(f"Alert method '{ALERT_METHOD}' invalid.")

# --- Simple Webhook Endpoint for tests ---
@app.route("/webhook", methods=["POST"])
def webhook_receiver():
    if WEBHOOK_API_KEY is None:
        logger.error("WEBHOOK_API_KEY not configured; rejecting request")
        return jsonify({"error": "Server misconfigured"}), 503
    if request.headers.get("X-API-Key") != WEBHOOK_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401
    payload = request.get_json() or {}
    redis_conn = get_redis_connection()
    if not redis_conn:
        return jsonify({"error": "Redis service unavailable"}), 503

    action = payload.get("action")
    ip = payload.get("ip")

    if action in {"block_ip", "allow_ip", "flag_ip", "unflag_ip"} and not ip:
        return jsonify({"error": f"Missing 'ip' in payload for action '{action}'."}), 400

    try:
        if action == "block_ip":
            redis_conn.sadd("blocklist", ip)
            return jsonify({"status": "success", "message": f"IP {ip} added to blocklist."})
        elif action == "allow_ip":
            redis_conn.srem("blocklist", ip)
            return jsonify({"status": "success", "message": f"IP {ip} removed from blocklist."})
        elif action == "flag_ip":
            reason = payload.get("reason", "")
            redis_conn.set(f"ip_flag:{ip}", reason)
            return jsonify({"status": "success", "message": f"IP {ip} flagged."})
        elif action == "unflag_ip":
            redis_conn.delete(f"ip_flag:{ip}")
            return jsonify({"status": "success", "message": f"IP {ip} unflagged."})
        else:
            return jsonify({"error": f"Invalid action: {action}"}), 400
    except Exception:
        logger.error("Failed to execute action", exc_info=True)
        return jsonify({"error": "Failed to execute action"}), 500



# --- Health Check Endpoint ---
@app.route("/health")
def health_check():
    redis_conn = get_redis_connection()
    if not redis_conn:
        return jsonify({"status": "error", "redis_connected": False}), 503
    try:
        redis_ok = bool(redis_conn.ping())
    except Exception:
        redis_ok = False
    status_code = 200 if redis_ok else 503
    return jsonify({"status": "ok" if redis_ok else "error", "redis_connected": redis_ok}), status_code

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("AI_SERVICE_PORT", 8000))
    workers = int(os.getenv("UVICORN_WORKERS", 2))
    log_level = os.getenv("LOG_LEVEL", "info").lower()

    logger.info("--- AI Service / Webhook Receiver Starting ---")
    # ... (startup logging remains the same) ...
    uvicorn.run("ai_webhook:app", host="0.0.0.0", port=port, workers=workers, log_level=log_level, reload=False)
    logger.info("--- AI Service / Webhook Receiver Started ---")
# Note: The above code is designed to be run as a FastAPI application.
# It should be run with a WSGI server like Uvicorn or Gunicorn.