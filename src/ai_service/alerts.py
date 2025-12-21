import asyncio
import json
import logging
import os
import pprint
import smtplib
import ssl
from email.mime.text import MIMEText
from functools import lru_cache
from typing import TYPE_CHECKING, Optional

import httpx
import redis.asyncio as redis

from src.shared.config import CONFIG
from src.shared.utils import LOG_DIR, log_error, log_event

try:
    from src.shared.http_alert import HttpAlertSender
    from src.shared.slack_alert import SlackAlertSender

    ALERT_ABSTRACTIONS_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback when optional deps missing
    ALERT_ABSTRACTIONS_AVAILABLE = False

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .main import WebhookEvent

logger = logging.getLogger(__name__)

ALERT_LOG_FILE = os.path.join(LOG_DIR, "alert_events.log")

ALERT_METHOD = CONFIG.ALERT_METHOD
ALERT_GENERIC_WEBHOOK_URL = CONFIG.ALERT_GENERIC_WEBHOOK_URL
ALERT_SLACK_WEBHOOK_URL = CONFIG.ALERT_SLACK_WEBHOOK_URL
ALERT_SMTP_HOST = CONFIG.ALERT_SMTP_HOST
ALERT_SMTP_PORT = CONFIG.ALERT_SMTP_PORT
ALERT_SMTP_USER = CONFIG.ALERT_SMTP_USER
ALERT_SMTP_PASSWORD_FILE = CONFIG.ALERT_SMTP_PASSWORD_FILE
ALERT_SMTP_USE_TLS = CONFIG.ALERT_SMTP_USE_TLS
ALERT_EMAIL_FROM = CONFIG.ALERT_EMAIL_FROM
ALERT_EMAIL_TO = CONFIG.ALERT_EMAIL_TO
ALERT_MIN_REASON_SEVERITY = CONFIG.ALERT_MIN_REASON_SEVERITY

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_DB = int(os.environ.get("REDIS_DB", 0))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD")
ANOMALY_EVENT_CHANNEL = "anomaly_events"


# ---------------------------------------------------------------------------
# SMTP password loader
# ---------------------------------------------------------------------------


@lru_cache()
def _load_smtp_password() -> Optional[str]:
    try:
        with open(ALERT_SMTP_PASSWORD_FILE, "r", encoding="utf-8") as f:
            value = f.read().strip()
            return value or None
    except FileNotFoundError as e:
        logger.warning(
            "SMTP password file not found at %s: %s", ALERT_SMTP_PASSWORD_FILE, e
        )
    except PermissionError as e:
        logger.error(
            "Permission denied reading SMTP password file at %s: %s",
            ALERT_SMTP_PASSWORD_FILE,
            e,
        )
    except OSError as e:
        logger.error(
            "OS error reading SMTP password file at %s: %s",
            ALERT_SMTP_PASSWORD_FILE,
            e,
        )
    except Exception as e:  # pragma: no cover - unexpected
        logger.error(
            "Unexpected error loading SMTP password from %s: %s",
            ALERT_SMTP_PASSWORD_FILE,
            e,
        )
    return None


# ---------------------------------------------------------------------------
# Alerting implementations
# ---------------------------------------------------------------------------


async def send_generic_webhook_alert(event_data: "WebhookEvent") -> None:
    """Send generic webhook alert using the layered alert abstraction."""
    if not ALERT_GENERIC_WEBHOOK_URL:
        return

    ip = event_data.details.get("ip", "N/A")

    if ALERT_ABSTRACTIONS_AVAILABLE:
        try:
            generic_sender = HttpAlertSender(
                webhook_url=ALERT_GENERIC_WEBHOOK_URL, timeout=10.0
            )
            alert_data = {
                "alert_type": "AI_DEFENSE_BLOCK",
                "reason": event_data.reason,
                "timestamp": str(event_data.timestamp_utc),
                "ip_address": ip,
                "user_agent": event_data.details.get("user_agent", "N/A"),
                "details": event_data.details,
            }
            success = await generic_sender.send_alert(alert_data)
            if success:
                log_event(
                    ALERT_LOG_FILE,
                    "ALERT_SENT_WEBHOOK",
                    {"reason": event_data.reason, "ip": ip},
                )
            else:
                log_error(
                    f"Failed to send generic webhook alert for IP {ip} using new alert system"
                )
        except Exception as e:  # pragma: no cover - fallback path
            log_error(
                f"Error using new generic alert system for IP {ip}, falling back to legacy",
                e,
            )
            await _send_generic_webhook_alert_legacy(event_data)
    else:
        await _send_generic_webhook_alert_legacy(event_data)


async def _send_generic_webhook_alert_legacy(event_data: "WebhookEvent") -> None:
    if not ALERT_GENERIC_WEBHOOK_URL:
        return

    ip = event_data.details.get("ip", "N/A")
    logger.info("Sending generic webhook alert (legacy) for IP: %s", ip)
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
            logger.info("Generic webhook alert sent successfully for IP %s.", ip)
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
    except Exception as e:  # pragma: no cover - unexpected
        log_error(f"Unexpected error sending generic webhook alert for IP {ip}", e)


async def send_slack_alert(event_data: "WebhookEvent") -> None:
    if not ALERT_SLACK_WEBHOOK_URL:
        return

    ip = event_data.details.get("ip", "N/A")
    reason = event_data.reason

    if ALERT_ABSTRACTIONS_AVAILABLE:
        try:
            slack_sender = SlackAlertSender(
                webhook_url=ALERT_SLACK_WEBHOOK_URL, timeout=10.0
            )
            alert_data = {
                "reason": reason,
                "event_type": event_data.event_type,
                "ip_address": ip,
                "user_agent": event_data.details.get("user_agent", "N/A"),
                "timestamp": str(event_data.timestamp_utc),
            }
            success = await slack_sender.send_slack_alert(alert_data)
            if success:
                log_event(
                    ALERT_LOG_FILE,
                    "ALERT_SENT_SLACK",
                    {"reason": reason, "ip": ip},
                )
            else:
                log_error(
                    f"Failed to send Slack alert for IP {ip} using new alert system"
                )
        except Exception as e:  # pragma: no cover - fallback path
            log_error(
                f"Error using new Slack alert system for IP {ip}, falling back to legacy",
                e,
            )
            await _send_slack_alert_legacy(event_data)
    else:
        await _send_slack_alert_legacy(event_data)


async def _send_slack_alert_legacy(event_data: "WebhookEvent") -> None:
    if not ALERT_SLACK_WEBHOOK_URL:
        return

    ip = event_data.details.get("ip", "N/A")
    ua = event_data.details.get("user_agent", "N/A")
    reason = event_data.reason

    logger.info("Sending Slack alert (legacy) for IP: %s", ip)
    message = (
        ":shield: *AI Defense Alert*\n> *Reason:* {reason}\n> *IP Address:* `{ip}`\n"
        f"> *User Agent:* `{ua}`\n> *Timestamp (UTC):* {event_data.timestamp_utc}"
    )
    payload = {"text": message}
    headers = {"Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                ALERT_SLACK_WEBHOOK_URL, headers=headers, json=payload
            )
            response.raise_for_status()
        logger.info("Slack alert sent successfully for IP %s.", ip)
        log_event(ALERT_LOG_FILE, "ALERT_SENT_SLACK", {"reason": reason, "ip": ip})
    except httpx.HTTPError as e:
        log_error(
            f"Failed to send Slack alert to {ALERT_SLACK_WEBHOOK_URL} for IP {ip}", e
        )
    except Exception as e:  # pragma: no cover - unexpected
        log_error(f"Unexpected error sending Slack alert for IP {ip}", e)


async def send_smtp_alert(event_data: "WebhookEvent") -> None:
    if not ALERT_EMAIL_TO or not ALERT_SMTP_HOST or not ALERT_EMAIL_FROM:
        log_error("SMTP alert config missing.")
        return

    ip = event_data.details.get("ip", "N/A")
    ua = event_data.details.get("user_agent", "N/A")
    reason = event_data.reason

    logger.info("Sending SMTP alert for IP: %s to %s", ip, ALERT_EMAIL_TO)
    subject = f"[AI Defense Alert] Suspicious Activity Detected - {reason}"
    body = f"""Suspicious activity detected:
Reason: {reason}
Timestamp (UTC): {event_data.timestamp_utc}
IP Address: {ip}
User Agent: {ua}
Details: {pprint.pformat(event_data.details)}
---
IP added to blocklist (TTL: {CONFIG.BLOCKLIST_TTL_SECONDS}s). Logs in {LOG_DIR}.
"""
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = ALERT_EMAIL_FROM
    msg["To"] = ALERT_EMAIL_TO

    def smtp_send_sync() -> None:
        smtp_conn = None
        try:
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
                smtp_conn.starttls(context=ssl.create_default_context())
            if ALERT_SMTP_USER:
                smtp_password = _load_smtp_password()
                if smtp_password:
                    smtp_conn.login(ALERT_SMTP_USER, smtp_password)
                else:
                    logger.warning(
                        "SMTP authentication skipped: ALERT_SMTP_USER is set but no password was provided. "
                        "Check SMTP configuration."
                    )
            from_addr = ALERT_EMAIL_FROM if ALERT_EMAIL_FROM else ""
            to_addrs = ALERT_EMAIL_TO.split(",") if ALERT_EMAIL_TO else []
            smtp_conn.sendmail(from_addr, to_addrs, msg.as_string())
            logger.info("SMTP alert sent for IP %s to %s.", ip, ALERT_EMAIL_TO)
            log_event(
                ALERT_LOG_FILE,
                "ALERT_SENT_SMTP",
                {"reason": reason, "ip": ip, "to": ALERT_EMAIL_TO},
            )
        except smtplib.SMTPException as e:
            log_error(f"SMTP error for IP {ip} (Host: {ALERT_SMTP_HOST})", e)
        except Exception as e:  # pragma: no cover - unexpected
            log_error(f"Unexpected SMTP error for IP {ip}", e)
        finally:
            if smtp_conn:
                try:
                    smtp_conn.quit()
                except Exception as e:  # pragma: no cover - cleanup failure
                    logger.error(f"Error quitting SMTP connection: {e}")

    try:
        await asyncio.to_thread(smtp_send_sync)
    except Exception as e:  # pragma: no cover - unexpected
        log_error(f"Error executing SMTP send thread for IP {ip}", e)


async def send_alert(event_data: "WebhookEvent") -> None:
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
            "Skipping alert for IP %s. Severity %s < Min %s",
            event_data.details.get("ip"),
            event_severity,
            min_severity,
        )
        return

    logger.info(
        "Dispatching alert for IP %s via method: %s (Severity: %s)",
        event_data.details.get("ip"),
        ALERT_METHOD,
        event_severity,
    )
    if ALERT_METHOD == "webhook":
        await send_generic_webhook_alert(event_data)
    elif ALERT_METHOD == "slack":
        await send_slack_alert(event_data)
    elif ALERT_METHOD == "smtp":
        await send_smtp_alert(event_data)
    elif ALERT_METHOD != "none":
        log_error(f"Alert method '{ALERT_METHOD}' invalid.")


# ---------------------------------------------------------------------------
# Redis Event-Driven Operations
# ---------------------------------------------------------------------------


async def get_redis_client():
    """Create and return an async Redis client."""
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True,
    )


async def subscribe_anomaly_events():
    """Subscribe to anomaly events from Redis Pub/Sub."""
    redis_client = await get_redis_client()
    try:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(ANOMALY_EVENT_CHANNEL)
        async for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    event_data = json.loads(message["data"])
                    await handle_anomaly_event(event_data)
                except json.JSONDecodeError as e:
                    logger.error("Failed to decode anomaly event: %s", e)
                except Exception as e:
                    logger.error("Error handling anomaly event: %s", e)
    finally:
        await redis_client.aclose()


async def handle_anomaly_event(event_data):
    """
    Process anomaly detection events from Redis Pub/Sub.

    This function receives high-score anomaly events and can trigger
    alerts or other defensive actions. Currently logs events; extend
    as needed to integrate with alerting or blocking systems.

    Args:
        event_data: Dictionary with 'anomaly_score' and 'features' keys

    Example implementation:
        anomaly_score = event_data.get('anomaly_score', 0)
        if anomaly_score > 0.9:
            event_data['reason'] = f"Critical Anomaly Score: {anomaly_score:.2f}"
            await send_alert(event_data)
    """
    logger.info("Received anomaly event: %s", event_data)
    # TODO: Implement alerting logic based on anomaly score and features


async def main():
    """Main entry point for the Redis subscriber."""
    # Await the Redis subscriber task to keep the event loop running
    await subscribe_anomaly_events()


if __name__ == "__main__":
    asyncio.run(main())
