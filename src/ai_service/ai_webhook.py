# ai_service/ai_webhook.py
# Receives webhook events, logs, blocklists via Redis (with TTL), optionally reports to community lists, and sends alerts.
"""Webhook receiver and blocklist manager.

This module implements the FastAPI application responsible for ingesting
webhook events from various detection points. Events may trigger IP
blocklisting in Redis, optional reporting to community services and alert
notifications through webhooks, Slack or SMTP email.
"""

import asyncio
import datetime
import ipaddress
import json
import logging
import os
import pprint
import smtplib
import ssl
from email.mime.text import MIMEText
from typing import Any, Dict, Optional, Union

import httpx
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from redis.exceptions import ConnectionError, RedisError

from src.shared.config import CONFIG, tenant_key
from src.shared.redis_client import get_redis_connection as shared_get_redis_connection

# --- Updated Metrics Import ---
try:
    from shared.metrics import increment_counter_metric  # Use the helper for counters
    from shared.metrics import (  # Add other specific metrics if ai_webhook needs to increment them directly
        COMMUNITY_REPORTS_ATTEMPTED,
        COMMUNITY_REPORTS_ERRORS_REQUEST,
        COMMUNITY_REPORTS_ERRORS_RESPONSE_DECODE,
        COMMUNITY_REPORTS_ERRORS_STATUS,
        COMMUNITY_REPORTS_ERRORS_TIMEOUT,
        COMMUNITY_REPORTS_ERRORS_UNEXPECTED,
        COMMUNITY_REPORTS_SUCCESS,
    )

    METRICS_SYSTEM_AVAILABLE = True
    logging.info(
        "Metrics system (prometheus client style) imported successfully by AI Webhook."
    )
except ImportError:
    logging.warning(
        "Could not import specific metrics or helper from metrics.py. Metric incrementation will be no-op."
    )

    # Define dummy functions/objects if metrics are unavailable to prevent runtime errors
    def increment_counter_metric(metric_instance, labels=None):
        pass

    class DummyCounter:
        def inc(self, amount=1):
            pass

    COMMUNITY_REPORTS_ATTEMPTED = DummyCounter()
    COMMUNITY_REPORTS_SUCCESS = DummyCounter()
    COMMUNITY_REPORTS_ERRORS_TIMEOUT = DummyCounter()
    COMMUNITY_REPORTS_ERRORS_REQUEST = DummyCounter()
    COMMUNITY_REPORTS_ERRORS_STATUS = DummyCounter()
    COMMUNITY_REPORTS_ERRORS_RESPONSE_DECODE = DummyCounter()
    COMMUNITY_REPORTS_ERRORS_UNEXPECTED = DummyCounter()
    METRICS_SYSTEM_AVAILABLE = False

# --- Setup Logging ---
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(levelname)s - %(message)s'
# )  # Already configured by FastAPI/Uvicorn
logger = logging.getLogger(__name__)  # Use __name__ for module-specific logger

# --- Configuration (remains the same) ---
REDIS_HOST = CONFIG.REDIS_HOST
REDIS_PORT = CONFIG.REDIS_PORT
REDIS_DB_BLOCKLIST = CONFIG.REDIS_DB_BLOCKLIST
BLOCKLIST_KEY_PREFIX = tenant_key("blocklist:ip:")
BLOCKLIST_TTL_SECONDS = CONFIG.BLOCKLIST_TTL_SECONDS

ALERT_METHOD = CONFIG.ALERT_METHOD
ALERT_GENERIC_WEBHOOK_URL = CONFIG.ALERT_GENERIC_WEBHOOK_URL
ALERT_SLACK_WEBHOOK_URL = CONFIG.ALERT_SLACK_WEBHOOK_URL
ALERT_SMTP_HOST = CONFIG.ALERT_SMTP_HOST
ALERT_SMTP_PORT = CONFIG.ALERT_SMTP_PORT
ALERT_SMTP_USER = CONFIG.ALERT_SMTP_USER
ALERT_SMTP_PASSWORD_FILE = CONFIG.ALERT_SMTP_PASSWORD_FILE
ALERT_SMTP_PASSWORD = CONFIG.ALERT_SMTP_PASSWORD
ALERT_SMTP_USE_TLS = CONFIG.ALERT_SMTP_USE_TLS
ALERT_EMAIL_FROM = CONFIG.ALERT_EMAIL_FROM
ALERT_EMAIL_TO = CONFIG.ALERT_EMAIL_TO
ALERT_MIN_REASON_SEVERITY = CONFIG.ALERT_MIN_REASON_SEVERITY

ENABLE_COMMUNITY_REPORTING = CONFIG.ENABLE_COMMUNITY_REPORTING
COMMUNITY_BLOCKLIST_REPORT_URL = CONFIG.COMMUNITY_BLOCKLIST_REPORT_URL
COMMUNITY_BLOCKLIST_API_KEY_FILE = CONFIG.COMMUNITY_BLOCKLIST_API_KEY_FILE
COMMUNITY_BLOCKLIST_REPORT_TIMEOUT = CONFIG.COMMUNITY_BLOCKLIST_REPORT_TIMEOUT
COMMUNITY_BLOCKLIST_API_KEY = CONFIG.COMMUNITY_BLOCKLIST_API_KEY

LOG_DIR = "/app/logs"
LOG_LEVEL = CONFIG.LOG_LEVEL
BLOCK_LOG_FILE = os.path.join(LOG_DIR, "block_events.log")
ALERT_LOG_FILE = os.path.join(LOG_DIR, "alert_events.log")
ERROR_LOG_FILE = os.path.join(LOG_DIR, "aiservice_errors.log")
COMMUNITY_REPORT_LOG_FILE = os.path.join(LOG_DIR, "community_report.log")
os.makedirs(LOG_DIR, exist_ok=True)
WEBHOOK_API_KEY = CONFIG.WEBHOOK_API_KEY

# --- Load Secrets ---
ALERT_SMTP_PASSWORD = CONFIG.ALERT_SMTP_PASSWORD
COMMUNITY_BLOCKLIST_API_KEY = CONFIG.COMMUNITY_BLOCKLIST_API_KEY

# --- Setup Clients & Validate Config ---
# Redis connection is initialized lazily to avoid network I/O on import.
# Blocklisting is disabled until a successful Redis connection is established.
BLOCKLISTING_ENABLED = False
redis_client_blocklist = None

if ALERT_METHOD == "smtp" and not ALERT_SMTP_PASSWORD and ALERT_SMTP_USER:
    logger.warning("SMTP alerting configured but SMTP password is not set.")
if ENABLE_COMMUNITY_REPORTING and not COMMUNITY_BLOCKLIST_REPORT_URL:
    logger.warning(
        "Community reporting enabled but COMMUNITY_BLOCKLIST_REPORT_URL is not set."
    )
if ENABLE_COMMUNITY_REPORTING and not COMMUNITY_BLOCKLIST_API_KEY:
    logger.warning(
        "Community reporting enabled but COMMUNITY_BLOCKLIST_API_KEY secret could not be loaded."
    )

# --- Pydantic Model ---


class WebhookEvent(BaseModel):
    event_type: str = Field(
        ..., description="Type of event, e.g., 'suspicious_activity_detected'"
    )
    reason: str = Field(
        ...,
        description="Reason for the event/block, e.g., 'High Combined Score (0.95)'",
    )
    # Allow str or datetime
    timestamp_utc: Union[str, datetime.datetime] = Field(
        ..., description="Timestamp of the original detection"
    )
    details: Dict[str, Any] = Field(
        ..., description="Detailed metadata about the request (IP, UA, headers, etc.)"
    )


# --- FastAPI App ---
app = FastAPI()


def get_redis_connection():
    """Return a Redis connection, creating it on first use with retries."""
    global redis_client_blocklist, BLOCKLISTING_ENABLED

    if redis_client_blocklist is None:
        try:
            redis_client_blocklist = shared_get_redis_connection(
                db_number=REDIS_DB_BLOCKLIST
            )
            if redis_client_blocklist:
                try:
                    redis_client_blocklist.ping()
                    BLOCKLISTING_ENABLED = True
                    logger.info(
                        f"Connected to Redis for blocklisting at {REDIS_HOST}:{REDIS_PORT}, DB: {REDIS_DB_BLOCKLIST}"
                    )
                except (ConnectionError, RedisError) as e:
                    logger.error(
                        f"Redis ping failed for Blocklisting: {e}. Blocklisting disabled."
                    )
                    BLOCKLISTING_ENABLED = False
                    redis_client_blocklist = None
            else:
                logger.error(
                    "Redis connection for blocklisting returned None. Blocklisting disabled."
                )
                BLOCKLISTING_ENABLED = False
        except (ConnectionError, RedisError) as e:
            logger.error(
                f"Redis connection failed for Blocklisting: {e}. Blocklisting disabled."
            )
            BLOCKLISTING_ENABLED = False
            redis_client_blocklist = None
        except Exception as e:
            logger.error(
                f"Unexpected error connecting to Redis for Blocklisting: {e}. Blocklisting disabled."
            )
            BLOCKLISTING_ENABLED = False
            redis_client_blocklist = None

    if not BLOCKLISTING_ENABLED:
        return None

    return redis_client_blocklist


# --- Helper Functions ---


def log_error(message: str, exception: Optional[Exception] = None):
    timestamp = (
        datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    )
    log_entry = f"{timestamp} - ERROR: {message}"
    if exception:
        log_entry += f" | Exception: {type(exception).__name__}: {exception}"
    logger.error(log_entry)
    try:
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
    except Exception as log_e:
        logger.critical(
            "FATAL: Could not write to error log file %s: %s | Original error: %s",
            ERROR_LOG_FILE,
            log_e,
            log_entry,
        )


def log_event(log_file: str, event_type: str, data: dict):
    try:
        serializable_data = json.loads(json.dumps(data, default=str))
        log_entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "event_type": event_type,
            **serializable_data,
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        log_error(f"Failed to write to log file {log_file}", e)


# --- Action Functions ---


def add_ip_to_blocklist(
    ip_address: str, reason: str, event_details: Optional[dict] = None
) -> bool:
    redis_conn = get_redis_connection()
    if (
        not BLOCKLISTING_ENABLED
        or not redis_conn
        or not ip_address
        or ip_address == "unknown"
    ):
        if ip_address == "unknown":
            logger.warning(
                f"Attempted to blocklist 'unknown' IP. Reason: {reason}. Details: {event_details}"
            )
        return False
    try:
        ipaddress.ip_address(ip_address)
    except ValueError:
        logger.warning(
            f"Attempted to blocklist invalid IP {ip_address}. Reason: {reason}. Details: {event_details}"
        )
        return False
    try:
        block_key = f"{BLOCKLIST_KEY_PREFIX}{ip_address}"
        block_metadata = json.dumps(
            {
                "reason": reason,
                "timestamp_utc": datetime.datetime.now(datetime.timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "user_agent": (
                    event_details.get("user_agent", "N/A") if event_details else "N/A"
                ),
            }
        )
        if redis_conn.exists(block_key):
            logger.info(f"IP {ip_address} already in blocklist. TTL refreshed")
        redis_conn.setex(block_key, BLOCKLIST_TTL_SECONDS, block_metadata)
        logger.info(
            "Added/Refreshed IP %s to Redis blocklist (Key: %s) with TTL %ss. "
            "Reason: %s",
            ip_address,
            block_key,
            BLOCKLIST_TTL_SECONDS,
            reason,
        )
        log_event(
            BLOCK_LOG_FILE,
            "BLOCKLIST_ADD_TTL",
            {
                "ip_address": ip_address,
                "reason": reason,
                "ttl_seconds": BLOCKLIST_TTL_SECONDS,
                "details": event_details,
            },
        )
        return True
    except RedisError as e:
        log_error(f"Redis error setting blocklist key for IP {ip_address}", e)
        return False
    except Exception as e:
        log_error(f"Unexpected error setting blocklist key for IP {ip_address}", e)
        return False


async def report_ip_to_community(ip: str, reason: str, details: dict) -> bool:
    if (
        not ENABLE_COMMUNITY_REPORTING
        or not COMMUNITY_BLOCKLIST_REPORT_URL
        or not COMMUNITY_BLOCKLIST_API_KEY
        or not ip
    ):
        if ENABLE_COMMUNITY_REPORTING and ip:
            logger.debug(
                f"Community reporting skipped for IP {ip}: URL or API Key not configured."
            )
        return False

    increment_counter_metric(COMMUNITY_REPORTS_ATTEMPTED)  # Use new metric object
    logger.info(
        f"Reporting IP {ip} to community blocklist: {COMMUNITY_BLOCKLIST_REPORT_URL}"
    )
    headers = {"Accept": "application/json", "Key": COMMUNITY_BLOCKLIST_API_KEY}
    categories = "18"  # Default: Brute-Force
    if "scan" in reason.lower():
        categories = "14"
    if (
        "scraping" in reason.lower()
        or "crawler" in reason.lower()
        or "llm" in reason.lower()
    ):
        categories = "19"
    if "honeypot" in reason.lower():
        categories = "22"
    comment = (
        "AI Defense Stack Detection. Reason: "
        f"{reason}. UA: {details.get('user_agent', 'N/A')}. "
        f"Path: {details.get('path', 'N/A')}"
    )
    payload = {
        "ip": ip,
        "categories": categories,
        "comment": comment[:1024],
    }
    response = None
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                COMMUNITY_BLOCKLIST_REPORT_URL,
                headers=headers,
                data=payload,
                timeout=COMMUNITY_BLOCKLIST_REPORT_TIMEOUT,
            )
            response.raise_for_status()
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(response.json),
                    COMMUNITY_BLOCKLIST_REPORT_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.error(
                    f"Timeout parsing community blocklist report response for IP {ip}"
                )
                increment_counter_metric(COMMUNITY_REPORTS_ERRORS_TIMEOUT)
                return False
            logger.info(
                f"Successfully reported IP {ip} to community blocklist. Response: {result}"
            )
            log_event(
                COMMUNITY_REPORT_LOG_FILE,
                "COMMUNITY_REPORT_SUCCESS",
                {"ip": ip, "reason": reason, "api_response": result},
            )
            increment_counter_metric(COMMUNITY_REPORTS_SUCCESS)  # Use new metric object
            return True
    except httpx.TimeoutException:
        logger.error(f"Timeout reporting IP {ip}")
        increment_counter_metric(COMMUNITY_REPORTS_ERRORS_TIMEOUT)
        return False
    except httpx.RequestError as exc:
        logger.error(f"Request error reporting IP {ip}: {exc}")
        increment_counter_metric(COMMUNITY_REPORTS_ERRORS_REQUEST)
        return False
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Community blocklist report failed for IP %s status %s. Response: %s",
            ip,
            exc.response.status_code,
            exc.response.text[:500],
        )
        increment_counter_metric(COMMUNITY_REPORTS_ERRORS_STATUS)
        return False
    except json.JSONDecodeError as exc:
        logger.error(
            "JSON decode error for IP %s: %s - Response: %s",
            ip,
            exc,
            (response.text[:500] if response else "No response"),
        )
        increment_counter_metric(COMMUNITY_REPORTS_ERRORS_RESPONSE_DECODE)
        return False
    except Exception as e:
        logger.error(f"Unexpected error reporting IP {ip}: {e}", exc_info=True)
        increment_counter_metric(COMMUNITY_REPORTS_ERRORS_UNEXPECTED)
        return False


# --- Alerting Functions (send_generic_webhook_alert, send_slack_alert, send_smtp_alert, send_alert) ---
# These functions remain largely the same, no direct metric calls in them.


async def send_generic_webhook_alert(event_data: WebhookEvent):
    if not ALERT_GENERIC_WEBHOOK_URL:
        return
    ip = event_data.details.get("ip", "N/A")
    logger.info(f"Sending generic webhook alert for IP: {ip}")
    payload = {
        "alert_type": "AI_DEFENSE_BLOCK",
        "reason": event_data.reason,
        "timestamp": str(event_data.timestamp_utc),
        "ip_address": ip,
        "user_agent": event_data.details.get("user_agent", "N/A"),
        "details": event_data.details,
    }
    try:
        json_payload = json.loads(json.dumps(payload, default=str))
        async with httpx.AsyncClient() as client:
            response = await client.post(
                ALERT_GENERIC_WEBHOOK_URL, json=json_payload, timeout=10.0
            )
            response.raise_for_status()
            logger.info(f"Generic webhook alert sent successfully for IP {ip}.")
            log_event(
                ALERT_LOG_FILE,
                "ALERT_SENT_WEBHOOK",
                {"reason": event_data.reason, "ip": ip},
            )
    except json.JSONDecodeError as e:
        log_error(f"Failed to serialize generic webhook payload for IP {ip}", e)
    except httpx.RequestError as e:
        log_error(
            f"Failed to send generic webhook alert to {ALERT_GENERIC_WEBHOOK_URL} for IP {ip}",
            e,
        )
    except httpx.HTTPStatusError as e:
        log_error(
            f"Generic webhook alert failed for IP {ip} with status {e.response.status_code}",
            e,
        )
    except Exception as e:
        log_error(f"Unexpected error sending generic webhook alert for IP {ip}", e)


async def send_slack_alert(event_data: WebhookEvent):
    if not ALERT_SLACK_WEBHOOK_URL:
        return
    ip = event_data.details.get("ip", "N/A")
    ua = event_data.details.get("user_agent", "N/A")
    reason = event_data.reason
    logger.info(f"Sending Slack alert for IP: {ip}")
    message = (
        ":shield: *AI Defense Alert*\n> *Reason:* {reason}\n> *IP Address:* `{ip}`\n"
        f"> *User Agent:* `{ua}`\n> *Timestamp (UTC):* {event_data.timestamp_utc}"
    )
    payload = {"text": message}
    headers = {"Content-Type": "application/json"}
    try:
        response = await asyncio.to_thread(
            requests.post,
            ALERT_SLACK_WEBHOOK_URL,
            headers=headers,
            json=payload,
            timeout=10.0,
        )
        response.raise_for_status()
        logger.info(f"Slack alert sent successfully for IP {ip}.")
        log_event(ALERT_LOG_FILE, "ALERT_SENT_SLACK", {"reason": reason, "ip": ip})
    except requests.exceptions.RequestException as e:
        log_error(
            f"Failed to send Slack alert to {ALERT_SLACK_WEBHOOK_URL} for IP {ip}", e
        )
    except Exception as e:
        log_error(f"Unexpected error sending Slack alert for IP {ip}", e)


async def send_smtp_alert(event_data: WebhookEvent):
    if not ALERT_EMAIL_TO or not ALERT_SMTP_HOST or not ALERT_EMAIL_FROM:
        log_error("SMTP alert config missing.")
        return
    ip = event_data.details.get("ip", "N/A")
    ua = event_data.details.get("user_agent", "N/A")
    reason = event_data.reason
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
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = ALERT_EMAIL_FROM
    msg["To"] = ALERT_EMAIL_TO

    def smtp_send_sync():
        smtp_conn = None
        try:
            if not ALERT_SMTP_HOST:
                logger.error("SMTP host not set.")
                return
            if ALERT_SMTP_PORT == 465:
                smtp_conn = smtplib.SMTP_SSL(
                    str(ALERT_SMTP_HOST),
                    ALERT_SMTP_PORT,
                    timeout=15,
                    context=ssl.create_default_context(),
                )
            else:
                smtp_conn = smtplib.SMTP(
                    str(ALERT_SMTP_HOST), ALERT_SMTP_PORT, timeout=15
                )
            if ALERT_SMTP_USE_TLS and ALERT_SMTP_PORT != 465:
                smtp_conn.starttls(
                    context=ssl.create_default_context()
                )  # Don't call starttls if already SSL
            if ALERT_SMTP_USER and ALERT_SMTP_PASSWORD:
                smtp_conn.login(ALERT_SMTP_USER, ALERT_SMTP_PASSWORD)
            elif ALERT_SMTP_USER:
                logger.warning("SMTP User provided but password missing.")
            from_addr = ALERT_EMAIL_FROM if ALERT_EMAIL_FROM else ""
            to_addrs = ALERT_EMAIL_TO.split(",") if ALERT_EMAIL_TO else []
            smtp_conn.sendmail(from_addr, to_addrs, msg.as_string())
            logger.info(f"SMTP alert sent for IP {ip} to {ALERT_EMAIL_TO}.")
            log_event(
                ALERT_LOG_FILE,
                "ALERT_SENT_SMTP",
                {"reason": reason, "ip": ip, "to": ALERT_EMAIL_TO},
            )
        except smtplib.SMTPException as e:
            log_error(f"SMTP error for IP {ip} (Host: {ALERT_SMTP_HOST})", e)
        except Exception as e:
            log_error(f"Unexpected SMTP error for IP {ip}", e)
        finally:
            if smtp_conn:
                try:
                    smtp_conn.quit()
                except Exception:
                    pass

    try:
        await asyncio.to_thread(smtp_send_sync)
    except Exception as e:
        log_error(f"Error executing SMTP send thread for IP {ip}", e)


async def send_alert(event_data: WebhookEvent):
    severity_map = {
        "High Heuristic": 1,
        "Local LLM": 2,
        "External API": 3,
        "High Combined": 1,
        "Honeypot_Hit": 2,
        "IP Reputation": 1,
    }
    reason_key = event_data.reason.split("(")[0].strip()
    event_severity = severity_map.get(reason_key, 0)
    min_severity_reason = ALERT_MIN_REASON_SEVERITY.split(" ")[0].strip()
    min_severity = severity_map.get(min_severity_reason, 1)
    if event_severity < min_severity:
        logger.debug(
            f"Skipping alert for IP {event_data.details.get('ip')}. Severity {event_severity} < Min {min_severity}"
        )
        return
    logger.info(
        f"Dispatching alert for IP {event_data.details.get('ip')} via method: {ALERT_METHOD} (Severity: {event_severity})"
    )
    if ALERT_METHOD == "webhook":
        await send_generic_webhook_alert(event_data)
    elif ALERT_METHOD == "slack":
        await send_slack_alert(event_data)
    elif ALERT_METHOD == "smtp":
        await send_smtp_alert(event_data)
    elif ALERT_METHOD != "none":
        log_error(f"Alert method '{ALERT_METHOD}' invalid.")


# --- Simple Webhook Endpoint for tests ---


@app.post("/webhook")
async def webhook_receiver(request: Request):
    """Handle blocklist/flag actions from the escalation engine tests."""
    api_key = request.headers.get("X-API-Key")
    if not WEBHOOK_API_KEY or api_key != WEBHOOK_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    payload = (
        await request.json()
        if request.headers.get("content-type", "").startswith("application/json")
        else {}
    )
    redis_conn = get_redis_connection()
    if not redis_conn:
        raise HTTPException(status_code=503, detail="Redis service unavailable")

    action = payload.get("action")
    ip = payload.get("ip")

    actions_requiring_ip = {"block_ip", "allow_ip", "flag_ip", "unflag_ip"}
    if action in actions_requiring_ip:
        if not ip:
            raise HTTPException(
                status_code=400,
                detail=f"Missing 'ip' in payload for action '{action}'.",
            )
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid IP address: {ip}")

    try:
        if action == "block_ip":
            redis_conn.sadd(tenant_key("blocklist"), ip)
            return {"status": "success", "message": f"IP {ip} added to blocklist."}
        elif action == "allow_ip":
            redis_conn.srem(tenant_key("blocklist"), ip)
            return {"status": "success", "message": f"IP {ip} removed from blocklist."}
        elif action == "flag_ip":
            reason = payload.get("reason", "")
            redis_conn.set(tenant_key(f"ip_flag:{ip}"), reason)
            return {"status": "success", "message": f"IP {ip} flagged."}
        elif action == "unflag_ip":
            redis_conn.delete(tenant_key(f"ip_flag:{ip}"))
            return {"status": "success", "message": f"IP {ip} unflagged."}
        else:
            raise HTTPException(status_code=400, detail=f"Invalid action: {action}")
    except HTTPException:
        raise
    except Exception:
        logger.error("Failed to execute action", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to execute action")


# --- Health Check Endpoint ---
@app.get("/health")
async def health_check():
    redis_conn = get_redis_connection()
    if not redis_conn:
        return JSONResponse(
            {"status": "error", "redis_connected": False}, status_code=503
        )
    try:
        redis_ok = bool(redis_conn.ping())
    except Exception:
        redis_ok = False
    status_code = 200 if redis_ok else 503
    return JSONResponse(
        {"status": "ok" if redis_ok else "error", "redis_connected": redis_ok},
        status_code=status_code,
    )


if __name__ == "__main__":
    import uvicorn

    port = CONFIG.AI_SERVICE_PORT
    workers = int(os.getenv("UVICORN_WORKERS", 2))
    log_level = CONFIG.LOG_LEVEL.lower()

    logger.info("--- AI Service / Webhook Receiver Starting ---")
    # ... (startup logging remains the same) ...
    uvicorn.run(
        "src.ai_service.ai_webhook:app",
        # Bind to localhost by default to reduce exposure
        host=os.getenv("WEBHOOK_HOST", "127.0.0.1"),
        port=port,
        workers=workers,
        log_level=log_level,
        reload=False,
    )
    logger.info("--- AI Service / Webhook Receiver Started ---")
# Note: The above code is designed to be run as a FastAPI application.
# It should be run with a WSGI server like Uvicorn or Gunicorn.
