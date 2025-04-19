# metrics.py
# Simple in-memory metrics tracking for the defense stack.

from collections import Counter
import datetime
import threading

# Use a thread-safe Counter for basic metrics
metrics_store = Counter()
# Lock for operations that might not be inherently atomic if extended
_lock = threading.Lock()

# Store the start time
start_time = datetime.datetime.utcnow()

def increment_metric(key: str, value: int = 1):
    """Increments a counter metric."""
    with _lock:
        metrics_store[key] += value
        # print(f"Metric incremented: {key} = {metrics_store[key]}") # Optional: Debug logging

def get_metrics() -> dict:
    """Returns a dictionary of all current metrics."""
    with _lock:
        # Add uptime calculation
        uptime_seconds = (datetime.datetime.utcnow() - start_time).total_seconds()
        current_metrics = dict(metrics_store)
        current_metrics["service_uptime_seconds"] = round(uptime_seconds, 2)
        current_metrics["last_updated_utc"] = datetime.datetime.utcnow().isoformat() + "Z"
        return current_metrics

def reset_metrics():
    """Resets all metrics (useful for testing)."""
    global start_time
    with _lock:
        metrics_store.clear()
        start_time = datetime.datetime.utcnow()
        print("Metrics have been reset.")

# --- Predefined Metric Keys (Examples) ---
# You can call increment_metric with any string key.
# Defining common keys here can help consistency.

# Escalation Engine Metrics
METRIC_ESCALATION_REQUESTS = "escalation_requests_received"
METRIC_HEURISTIC_CHECKS = "heuristic_checks_run"
METRIC_LOCAL_LLM_CHECKS = "local_llm_checks_run"
METRIC_EXTERNAL_API_CHECKS = "external_api_checks_run"
METRIC_BOTS_DETECTED_HEURISTIC = "bots_detected_heuristic"
METRIC_BOTS_DETECTED_LOCAL_LLM = "bots_detected_local_llm"
METRIC_BOTS_DETECTED_EXTERNAL_API = "bots_detected_external_api"
METRIC_HUMANS_DETECTED_LOCAL_LLM = "humans_detected_local_llm"
METRIC_HUMANS_DETECTED_EXTERNAL_API = "humans_detected_external_api"
METRIC_WEBHOOKS_SENT = "webhooks_sent"
METRIC_WEBHOOK_ERRORS = "webhook_errors_request" # Or more specific errors
METRIC_LLM_ERRORS = "local_llm_errors_unexpected" # Or more specific errors

# Tarpit Metrics
METRIC_TAR PIT_HITS = "tarpit_hits"
METRIC_IP_FLAGGED = "tarpit_ips_flagged"

# Other potential metrics
# METRIC_REGISTRATION_ATTEMPTS = "registration_attempts"
# METRIC_SUSPICIOUS_EMAILS = "suspicious_emails_detected"


# Example of incrementing at import time (if desired, though typically done in service logic)
# increment_metric("module_loads_metrics")