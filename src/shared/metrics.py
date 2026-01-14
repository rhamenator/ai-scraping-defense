# metrics.py
"""Prometheus metrics used across services.

When Prometheus is unavailable, a lightweight in-memory counter is used so
metrics remain meaningful. Only the minimal interface required by the helper
functions is implemented.
"""

import time
from collections import defaultdict


class InMemoryCounter:
    """Simple in-memory counter supporting optional labels."""

    def __init__(self, name: str | None = None) -> None:
        self._name = name
        self._count = 0
        self._label_counts: dict[tuple[tuple[str, str], ...], int] = defaultdict(int)

    def inc(self) -> None:
        self._count += 1

    def labels(self, **labels):
        key = tuple(sorted(labels.items()))
        return _InMemoryCounterChild(self, key)

    def get(self, **labels) -> int:
        if labels:
            key = tuple(sorted(labels.items()))
            return self._label_counts.get(key, 0)
        return self._count


class _InMemoryCounterChild:
    def __init__(self, parent: InMemoryCounter, key: tuple[tuple[str, str], ...]):
        self._parent = parent
        self._key = key

    def inc(self) -> None:
        self._parent._label_counts[self._key] += 1


try:  # pragma: no cover - exercised in fallback test
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
except ImportError:  # pragma: no cover

    class CollectorRegistry:
        """Minimal registry storing counters for fallback metrics."""

        def __init__(self) -> None:
            self._metrics: dict[str, InMemoryCounter] = {}

        def register(self, metric: "InMemoryCounter") -> None:
            self._metrics[metric._name] = metric

    class Counter(InMemoryCounter):
        def __init__(self, name, documentation, labelnames=None, registry=None):
            super().__init__(name)
            self._documentation = documentation
            if registry is not None:
                registry.register(self)

    class Gauge:
        def __init__(self, name, documentation, labelnames=None, registry=None):
            self._name = name
            self._value = 0

        def labels(self, **labels):
            return self

        def set(self, value):
            self._value = value

        def inc(self):
            self._value += 1

        def dec(self):
            self._value -= 1

    class Histogram:
        def __init__(
            self, name, documentation, labelnames=None, registry=None, buckets=None
        ):
            self._name = name

        def labels(self, **labels):
            return self

        def observe(self, value):
            pass

        def time(self):
            def decorator(func):
                return func

            return decorator

    def generate_latest(registry):
        lines = []
        for metric in getattr(registry, "_metrics", {}).values():
            lines.append(
                f"# HELP {metric._name} {getattr(metric, '_documentation', '')}"
            )
            lines.append(f"# TYPE {metric._name} counter")
            lines.append(f"{metric._name}_total {metric.get()}")
            for labels, value in metric._label_counts.items():
                label_str = ",".join(f'{k}="{v}"' for k, v in labels)
                lines.append(
                    f"{metric._name}_total{{{label_str}}} {value}"  # include labeled metrics
                )
        return "\n".join(lines).encode()


# 0. Global Registry
REGISTRY = CollectorRegistry()

# 1. Counters

# General Counters (from previous versions)
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests.",
    ["method", "endpoint", "status_code"],
    registry=REGISTRY,
)
PAGE_VIEWS = Counter(
    "page_views_total", "Total page views.", ["page_type"], registry=REGISTRY
)
# ... (other general counters from metrics_py_for_test_v3 remain here) ...
CACHE_HITS = Counter("cache_hits_total", "Total cache hits.", registry=REGISTRY)
CACHE_MISSES = Counter("cache_misses_total", "Total cache misses.", registry=REGISTRY)
DB_QUERIES = Counter(
    "db_queries_total", "Total database queries.", ["query_type"], registry=REGISTRY
)
ERROR_COUNT = Counter(
    "errors_total", "Total errors encountered.", ["error_type"], registry=REGISTRY
)
SECURITY_EVENTS = Counter(
    "security_events_total", "Total security events.", ["event_type"], registry=REGISTRY
)
LOGIN_ATTEMPTS = Counter(
    "login_attempts_total", "Total login attempts.", ["result"], registry=REGISTRY
)
USER_REGISTRATIONS = Counter(
    "user_registrations_total", "Total user registrations.", registry=REGISTRY
)
API_CALLS = Counter(
    "api_calls_total", "Total API calls.", ["api_name", "version"], registry=REGISTRY
)
EXTERNAL_API_CALLS = Counter(
    "external_api_calls_total",
    "Total external API calls.",
    ["service_name"],
    registry=REGISTRY,
)
FILE_UPLOADS = Counter(
    "file_uploads_total", "Total file uploads.", ["file_type"], registry=REGISTRY
)
EMAIL_SENT = Counter(
    "email_sent_total", "Total emails sent.", ["email_type"], registry=REGISTRY
)
TARPIT_ENTRIES = Counter(
    "tarpit_entries_total", "Total entries into the tarpit.", registry=REGISTRY
)
HONEYPOT_TRIGGERS = Counter(
    "honeypot_triggers_total",
    "Total honeypot triggers.",
    ["honeypot_name"],
    registry=REGISTRY,
)


# Counters for AI Webhook (from metrics_py_for_test_v3)
COMMUNITY_REPORTS_ATTEMPTED = Counter(
    "community_reports_attempted_total",
    "Total attempts to report IPs to community blocklists.",
    registry=REGISTRY,
)
COMMUNITY_REPORTS_SUCCESS = Counter(
    "community_reports_success_total",
    "Total successful reports to community blocklists.",
    registry=REGISTRY,
)
COMMUNITY_REPORTS_ERRORS_TIMEOUT = Counter(
    "community_reports_errors_timeout_total",
    "Total timeout errors during community blocklist reporting.",
    registry=REGISTRY,
)
COMMUNITY_REPORTS_ERRORS_REQUEST = Counter(
    "community_reports_errors_request_total",
    "Total request errors during community blocklist reporting.",
    registry=REGISTRY,
)
COMMUNITY_REPORTS_ERRORS_STATUS = Counter(
    "community_reports_errors_status_total",
    "Total HTTP status errors from community blocklist API.",
    registry=REGISTRY,
)
COMMUNITY_REPORTS_ERRORS_RESPONSE_DECODE = Counter(
    "community_reports_errors_response_decode_total",
    "Total errors decoding responses from community blocklist API.",
    registry=REGISTRY,
)
COMMUNITY_REPORTS_ERRORS_UNEXPECTED = Counter(
    "community_reports_errors_unexpected_total",
    "Total unexpected errors during community blocklist reporting.",
    registry=REGISTRY,
)

# Counters for Escalation Engine
REDIS_ERRORS_FREQUENCY = Counter(
    "redis_errors_frequency_total",
    "Total Redis errors during frequency tracking.",
    registry=REGISTRY,
)
IP_REPUTATION_CHECKS_RUN = Counter(
    "ip_reputation_checks_run_total",
    "Total IP reputation checks performed.",
    registry=REGISTRY,
)
IP_REPUTATION_SUCCESS = Counter(
    "ip_reputation_success_total",
    "Total successful IP reputation checks.",
    registry=REGISTRY,
)
IP_REPUTATION_MALICIOUS = Counter(
    "ip_reputation_malicious_total",
    "Total IPs flagged as malicious by reputation service.",
    registry=REGISTRY,
)
IP_REPUTATION_ERRORS_TIMEOUT = Counter(
    "ip_reputation_errors_timeout_total",
    "Total timeout errors during IP reputation checks.",
    registry=REGISTRY,
)
IP_REPUTATION_ERRORS_REQUEST = Counter(
    "ip_reputation_errors_request_total",
    "Total request errors during IP reputation checks.",
    registry=REGISTRY,
)
IP_REPUTATION_ERRORS_RESPONSE_DECODE = Counter(
    "ip_reputation_errors_response_decode_total",
    "Total errors decoding IP reputation API responses.",
    registry=REGISTRY,
)
IP_REPUTATION_ERRORS_UNEXPECTED = Counter(
    "ip_reputation_errors_unexpected_total",
    "Total unexpected errors during IP reputation checks.",
    registry=REGISTRY,
)

HEURISTIC_CHECKS_RUN = Counter(
    "heuristic_checks_run_total",
    "Total heuristic checks performed by escalation engine.",
    registry=REGISTRY,
)
# Note: The dynamic f"req_freq_{FREQUENCY_WINDOW_SECONDS}s" metric is complex for a simple counter.
# Escalation engine should increment a general counter per analysis, and
# actual frequencies might be better as observed values in a Histogram.
# For now, a general counter for frequency analyses performed:
FREQUENCY_ANALYSES_PERFORMED = Counter(
    "frequency_analyses_performed_total",
    "Total frequency analyses performed.",
    registry=REGISTRY,
)

RF_MODEL_PREDICTIONS = Counter(
    "rf_model_predictions_total",
    "Total predictions made by the Random Forest model.",
    registry=REGISTRY,
)
RF_MODEL_ERRORS = Counter(
    "rf_model_errors_total",
    "Total errors during Random Forest model prediction.",
    registry=REGISTRY,
)
SCORE_ADJUSTED_IP_REPUTATION = Counter(
    "score_adjusted_ip_reputation_total",
    "Total times final score was adjusted due to IP reputation.",
    registry=REGISTRY,
)

LOCAL_LLM_CHECKS_RUN = Counter(
    "local_llm_checks_run_total",
    "Total checks made using local LLM.",
    registry=REGISTRY,
)
LOCAL_LLM_ERRORS_UNEXPECTED_RESPONSE = Counter(
    "local_llm_errors_unexpected_response_total",
    "Total unexpected responses from local LLM.",
    registry=REGISTRY,
)
LOCAL_LLM_ERRORS_TIMEOUT = Counter(
    "local_llm_errors_timeout_total",
    "Total timeout errors calling local LLM.",
    registry=REGISTRY,
)
LOCAL_LLM_ERRORS_REQUEST = Counter(
    "local_llm_errors_request_total",
    "Total request errors calling local LLM.",
    registry=REGISTRY,
)
LOCAL_LLM_ERRORS_RESPONSE_DECODE = Counter(
    "local_llm_errors_response_decode_total",
    "Total errors decoding local LLM responses.",
    registry=REGISTRY,
)
LOCAL_LLM_ERRORS_UNEXPECTED = Counter(
    "local_llm_errors_unexpected_total",
    "Total unexpected errors with local LLM.",
    registry=REGISTRY,
)

EXTERNAL_API_CHECKS_RUN = Counter(
    "external_api_checks_run_total",
    "Total checks made using external classification API.",
    registry=REGISTRY,
)
EXTERNAL_API_SUCCESS = Counter(
    "external_api_success_total",
    "Total successful calls to external classification API.",
    registry=REGISTRY,
)
EXTERNAL_API_ERRORS_UNEXPECTED_RESPONSE = Counter(
    "external_api_errors_unexpected_response_total",
    "Total unexpected responses from external API.",
    registry=REGISTRY,
)
EXTERNAL_API_ERRORS_TIMEOUT = Counter(
    "external_api_errors_timeout_total",
    "Total timeout errors calling external API.",
    registry=REGISTRY,
)
EXTERNAL_API_ERRORS_REQUEST = Counter(
    "external_api_errors_request_total",
    "Total request errors calling external API.",
    registry=REGISTRY,
)
EXTERNAL_API_ERRORS_RESPONSE_DECODE = Counter(
    "external_api_errors_response_decode_total",
    "Total errors decoding external API responses.",
    registry=REGISTRY,
)
EXTERNAL_API_ERRORS_UNEXPECTED = Counter(
    "external_api_errors_unexpected_total",
    "Total unexpected errors with external API.",
    registry=REGISTRY,
)

ESCALATION_WEBHOOKS_SENT = Counter(
    "escalation_webhooks_sent_total",
    "Total webhooks sent by escalation engine.",
    registry=REGISTRY,
)
ESCALATION_WEBHOOK_ERRORS_REQUEST = Counter(
    "escalation_webhook_errors_request_total",
    "Total request errors sending escalation webhooks.",
    registry=REGISTRY,
)
ESCALATION_WEBHOOK_ERRORS_UNEXPECTED = Counter(
    "escalation_webhook_errors_unexpected_total",
    "Total unexpected errors sending escalation webhooks.",
    registry=REGISTRY,
)

CAPTCHA_CHALLENGES_TRIGGERED = Counter(
    "captcha_challenges_triggered_total",
    "Total CAPTCHA challenges triggered.",
    registry=REGISTRY,
)
ESCALATION_REQUESTS_RECEIVED = Counter(
    "escalation_requests_received_total",
    "Total number of requests received by the escalation engine",
    registry=REGISTRY,
)

BOTS_DETECTED_IP_REPUTATION = Counter(
    "bots_detected_ip_reputation_total",
    "Total bots detected primarily by IP reputation.",
    registry=REGISTRY,
)
BOTS_DETECTED_HIGH_SCORE = Counter(
    "bots_detected_high_score_total",
    "Total bots detected by high combined score.",
    registry=REGISTRY,
)
HUMANS_DETECTED_LOW_SCORE = Counter(
    "humans_detected_low_score_total",
    "Total classified as human by low combined score.",
    registry=REGISTRY,
)
BOTS_DETECTED_LOCAL_LLM = Counter(
    "bots_detected_local_llm_total",
    "Total bots detected by local LLM.",
    registry=REGISTRY,
)
HUMANS_DETECTED_LOCAL_LLM = Counter(
    "humans_detected_local_llm_total",
    "Total classified as human by local LLM.",
    registry=REGISTRY,
)
BOTS_DETECTED_EXTERNAL_API = Counter(
    "bots_detected_external_api_total",
    "Total bots detected by external API.",
    registry=REGISTRY,
)
HUMANS_DETECTED_EXTERNAL_API = Counter(
    "humans_detected_external_api_total",
    "Total classified as human by external API.",
    registry=REGISTRY,
)


# 2. Histograms (from previous versions)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "endpoint"],
    registry=REGISTRY,
)
DB_QUERY_LATENCY = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds.",
    ["query_type"],
    registry=REGISTRY,
)
EXTERNAL_API_LATENCY = Histogram(
    "external_api_latency_seconds",
    "Latency of external API calls in seconds.",
    ["service_name"],
    registry=REGISTRY,
)
FUNCTION_EXECUTION_TIME = Histogram(
    "function_execution_seconds",
    "Execution time of specific functions in seconds.",
    ["function_name"],
    registry=REGISTRY,
)
FILE_UPLOAD_SIZE = Histogram(
    "file_upload_size_bytes",
    "Size of uploaded files in bytes.",
    ["file_type"],
    registry=REGISTRY,
)
RESPONSE_SIZE = Histogram(
    "response_size_bytes",
    "Size of HTTP responses in bytes.",
    ["endpoint"],
    registry=REGISTRY,
)

# 3. Gauges (from previous versions)
ACTIVE_USERS = Gauge(
    "active_users_current", "Current number of active users.", registry=REGISTRY
)
CPU_USAGE = Gauge(
    "cpu_usage_percent", "Current CPU usage.", ["core"], registry=REGISTRY
)
MEMORY_USAGE = Gauge(
    "memory_usage_bytes", "Current memory usage in bytes.", ["type"], registry=REGISTRY
)
DISK_SPACE_USAGE = Gauge(
    "disk_space_usage_bytes",
    "Disk space usage by mount point.",
    ["mount_point"],
    registry=REGISTRY,
)
DB_CONNECTIONS = Gauge(
    "db_connections_active",
    "Active database connections.",
    ["db_name", "state"],
    registry=REGISTRY,
)
QUEUE_LENGTH = Gauge(
    "queue_length_current",
    "Current length of a queue.",
    ["queue_name"],
    registry=REGISTRY,
)
MODEL_VERSION_INFO = Gauge(
    "model_version_info",
    "Version of the ML model in use.",
    ["version"],
    registry=REGISTRY,
)
UPTIME_SECONDS = Gauge(
    "uptime_seconds_total", "System uptime in seconds.", registry=REGISTRY
)
CELERY_WORKERS = Gauge(
    "celery_workers_active", "Number of active Celery workers.", registry=REGISTRY
)
CELERY_TASKS = Gauge(
    "celery_tasks_total",
    "Number of Celery tasks by state.",
    ["state"],
    registry=REGISTRY,
)
FEATURE_FLAGS = Gauge(
    "feature_flags_status",
    "Status of feature flags (1=on, 0=off).",
    ["flag_name"],
    registry=REGISTRY,
)

# Performance Analytics Metrics
PERFORMANCE_BASELINE = Gauge(
    "performance_baseline_value",
    "Baseline performance values for comparison.",
    ["metric_name", "service"],
    registry=REGISTRY,
)
PERFORMANCE_ANOMALY_SCORE = Gauge(
    "performance_anomaly_score",
    "Current anomaly score for performance metrics.",
    ["metric_name", "service"],
    registry=REGISTRY,
)
PERFORMANCE_TREND = Gauge(
    "performance_trend",
    "Performance trend indicator (-1=declining, 0=stable, 1=improving).",
    ["metric_name", "service"],
    registry=REGISTRY,
)
PERFORMANCE_PERCENTILE = Histogram(
    "performance_percentile_seconds",
    "Performance percentile measurements.",
    ["metric_name", "service"],
    registry=REGISTRY,
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
)
PERFORMANCE_SAMPLES_COLLECTED = Counter(
    "performance_samples_collected_total",
    "Total performance samples collected for analytics.",
    ["metric_name", "service"],
    registry=REGISTRY,
)
PERFORMANCE_PREDICTIONS_GENERATED = Counter(
    "performance_predictions_generated_total",
    "Total performance predictions generated.",
    ["prediction_type", "service"],
    registry=REGISTRY,
)
PERFORMANCE_INSIGHTS_GENERATED = Counter(
    "performance_insights_generated_total",
    "Total performance insights generated.",
    ["insight_type", "service"],
    registry=REGISTRY,
)
PERFORMANCE_DEGRADATION_DETECTED = Counter(
    "performance_degradation_detected_total",
    "Total performance degradations detected.",
    ["metric_name", "service"],
    registry=REGISTRY,
)


# 4. Helper Functions (from previous versions)
def record_request(method, endpoint, status_code):
    REQUEST_COUNT.labels(
        method=method, endpoint=endpoint, status_code=str(status_code)
    ).inc()


@REQUEST_LATENCY.labels(method="GET", endpoint="/example").time()
def example_timed_request_handler():
    time.sleep(0.1)


def observe_histogram_metric(metric_instance, value, labels=None):
    if not isinstance(metric_instance, Histogram):
        raise TypeError("observe_histogram_metric requires a Histogram")
    if labels:
        metric_instance.labels(**labels).observe(value)
    else:
        metric_instance.observe(value)


def increment_counter_metric(metric_instance, labels=None):
    if not isinstance(metric_instance, (Counter, InMemoryCounter)):
        raise TypeError("increment_counter_metric requires a Counter")
    if labels:
        metric_instance.labels(**labels).inc()
    else:
        metric_instance.inc()


def set_gauge_metric(metric_instance, value, labels=None):
    if not isinstance(metric_instance, Gauge):
        raise TypeError("set_gauge_metric requires a Gauge")
    if labels:
        metric_instance.labels(**labels).set(value)
    else:
        metric_instance.set(value)


def increment_gauge_metric(metric_instance, labels=None):
    if not isinstance(metric_instance, Gauge):
        raise TypeError("increment_gauge_metric requires a Gauge")
    if labels:
        metric_instance.labels(**labels).inc()
    else:
        metric_instance.inc()


def decrement_gauge_metric(metric_instance, labels=None):
    if not isinstance(metric_instance, Gauge):
        raise TypeError("decrement_gauge_metric requires a Gauge")
    if labels:
        metric_instance.labels(**labels).dec()
    else:
        metric_instance.dec()


def get_metrics():
    return generate_latest(REGISTRY)


if __name__ == "__main__":
    # Example usage
    increment_counter_metric(ESCALATION_REQUESTS_RECEIVED)
    increment_counter_metric(RF_MODEL_PREDICTIONS)
    print(get_metrics().decode())
