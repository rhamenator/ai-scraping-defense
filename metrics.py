# anti_scrape/metrics.py
# Simple in-memory metrics tracking for the defense stack.

from collections import Counter
import datetime
import threading
import json
import os
import schedule
import time
import logging

# --- Configuration ---
LOG_METRICS_TO_JSON = os.getenv("LOG_METRICS_TO_JSON", "false").lower() == "true"
METRICS_JSON_FILE = os.getenv("METRICS_JSON_FILE", "/app/logs/metrics_dump.json")
METRICS_DUMP_INTERVAL_MIN = int(os.getenv("METRICS_DUMP_INTERVAL_MIN", 60)) # Dump every hour by default

logger = logging.getLogger(__name__)

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
        # logger.debug(f"Metric incremented: {key} = {metrics_store[key]}") # Optional: Debug logging

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
        logger.info("Metrics have been reset.")

# --- JSON Logging ---
def dump_metrics_to_json(filepath=METRICS_JSON_FILE):
    """Dumps the current metrics store to a JSON file."""
    if not LOG_METRICS_TO_JSON:
        return # Do nothing if not enabled

    logger.info(f"Dumping metrics to {filepath}...")
    try:
        metrics_snapshot = get_metrics() # Get current metrics including uptime etc.
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(metrics_snapshot, f, indent=2)
        logger.info(f"Metrics successfully dumped to {filepath}")
    except Exception as e:
        logger.error(f"ERROR: Failed to dump metrics to JSON file {filepath}: {e}")

def run_scheduled_dump():
    """Runs the metric dump function according to schedule."""
    dump_metrics_to_json()

# --- Metrics Scheduler (Run in one of the services, e.g., admin_ui or ai_service) ---
def start_metrics_scheduler():
    """Starts the background scheduler for dumping metrics if enabled."""
    if LOG_METRICS_TO_JSON:
        logger.info(f"Scheduling metrics JSON dump every {METRICS_DUMP_INTERVAL_MIN} minutes to {METRICS_JSON_FILE}")
        schedule.every(METRICS_DUMP_INTERVAL_MIN).minutes.do(run_scheduled_dump)

        # Run the scheduler in a separate thread
        def run_continuously():
            while True:
                schedule.run_pending()
                time.sleep(30) # Check every 30 seconds

        scheduler_thread = threading.Thread(target=run_continuously, daemon=True)
        scheduler_thread.start()
        logger.info("Metrics dump scheduler thread started.")
    else:
        logger.info("JSON metrics logging is disabled.")

# --- Predefined Metric Keys (Examples remain the same) ---
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
METRIC_WEBHOOK_ERRORS = "webhook_errors_request"
METRIC_LLM_ERRORS = "local_llm_errors_unexpected"
METRIC_TARPIT_HITS = "tarpit_hits"
METRIC_IP_FLAGGED = "tarpit_ips_flagged"

# Example: How to start the scheduler from another module
# if __name__ == "__main__":
#     # This part would typically be called from the main entry point of a service
#     print("Starting metrics scheduler (example)...")
#     start_metrics_scheduler()
#     # Keep the main thread alive or let the service run its course
#     try:
#         while True: time.sleep(1)
#     except KeyboardInterrupt:
#         print("Stopping scheduler example.")