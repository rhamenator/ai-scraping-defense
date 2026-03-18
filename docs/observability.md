# Observability Framework

The microservices in the AI Scraping Defense stack now share a common
observability layer that exposes structured logs, Prometheus metrics, request
traces, and aggregated health checks.  The goal is to make each service
production-ready out of the box and to provide consistent primitives for
incident response.

## Request Lifecycle

* **Structured logging** – All services emit JSON logs with `service`,
  `request_id`, `trace_id`, and `span_id` fields.  Logs can be shipped to Loki,
  Elastic, or any aggregator capable of parsing JSON.
* **Metrics** – HTTP request counters and latency histograms are captured via
  `src.shared.metrics`.  A `/metrics` endpoint is exposed on every service for
  Prometheus scraping.
* **Tracing** – Lightweight spans are recorded for each request and stored in
  an in-memory ring buffer accessible via `/observability/traces`.  Spans can
  be exported downstream or consumed during debugging.
* **Health checks** – The `/health` endpoint aggregates service-specific
  checks and returns `ok`, `degraded`, or `error` with per-check status to
  support readiness/liveness probes.

## Service Instrumentation

The shared middleware wires instrumentation when `create_app` is called.  Each
service can register checks or spans via `src.shared.observability`:

```python
from src.shared.observability import register_health_check, trace_span

app = create_app(title="Example Service")

@register_health_check(app, "redis")
async def redis_health():
    ...

with trace_span("example.operation", attributes={"foo": "bar"}):
    ...
```

## Performance Analytics

The observability framework now includes comprehensive performance analytics
capabilities for tracking, analyzing, and predicting service performance:

### Features

* **Automatic Data Collection** – Request latencies are automatically recorded
  and tracked over time with configurable history windows.
* **Baseline Tracking** – Set performance baselines for metrics to enable
  deviation detection and anomaly scoring.
* **Trend Analysis** – Calculate performance trends using linear regression to
  identify degrading or improving metrics.
* **Anomaly Detection** – Automatic detection of performance degradations when
  metrics exceed baseline thresholds (e.g., 50% increase).
* **Performance Insights** – Automatically generated insights about
  performance issues with severity levels and metadata.
* **Predictive Analytics** – Support for generating performance predictions
  for capacity planning and forecasting.

### Using Performance Analytics

```python
from src.shared.observability import get_performance_analytics

# Access the performance analytics instance
analytics = get_performance_analytics()

# Set a baseline for a metric
analytics.set_baseline("api_latency", 0.1)

# Record a performance sample with percentiles
analytics.record_metric(
    "api_latency",
    0.15,
    percentiles={"p50": 0.12, "p95": 0.18, "p99": 0.22}
)

# Calculate performance trend
trend = analytics.calculate_trend("api_latency")

# Generate a prediction
prediction = analytics.generate_prediction(
    metric_name="api_latency",
    prediction_type="capacity",
    predicted_value=0.25,
    confidence=0.85,
    forecast_horizon="1h"
)
```

### Performance Analytics Endpoints

Three new endpoints are available on all services:

* **`/observability/performance/insights`** – Returns recent performance
  insights including detected degradations and anomalies.
* **`/observability/performance/predictions`** – Returns recent performance
  predictions for capacity planning.
* **`/observability/performance/history`** – Returns historical performance
  data with optional filtering by metric name.

Example:

```bash
curl http://localhost:8000/observability/performance/insights?limit=20
curl http://localhost:8000/observability/performance/history?metric_name=request_latency_/api/endpoint&limit=100
```

## Metrics and Traces

* **Prometheus** – Scrape `/metrics` and import `monitoring/prometheus.yml` into
  your Prometheus server.  Grafana dashboards can be built on top of the
  standard HTTP metrics.
* **Traces** – Fetch recent spans via `/observability/traces?limit=200`.  The
  payload is JSON and can be pushed to Tempo, Jaeger, or any trace store.  The
  buffer size is configurable via the `OBS_TRACE_HISTORY` environment variable
  (defaults to 512).

## Health Check Contract

The health endpoint returns:


{
  "status": "ok",
  "service": "ai-service",
  "timestamp": "2024-04-12T15:04:05Z",
  "checks": {
    "redis": {"status": "ok", "detail": {"cache_keys": 128}}
  }
}


`status` becomes `degraded` when non-critical checks fail and `error` when any
critical check fails.  Kubernetes probes and load balancers should consume
this endpoint.

## Operational Playbook

1. Scrape `/metrics` for Prometheus and configure alerting on latency,
    `http_requests_total`, and service-specific counters.
2. Collect logs with a JSON-aware shipper (Filebeat, Fluent Bit, Vector) and
    correlate using `trace_id`.
3. Periodically export `/observability/traces` to verify span fidelity and
    ensure end-to-end timing stays within SLO thresholds.
4. Use the `scripts/operations_toolkit.py` automation to schedule health
    drills that verify logs, metrics, and traces continue to flow during
    failover tests.

## Related Operations Docs

* `monitoring_stack.md` covers Prometheus/Grafana deployment topology.
* `operations_playbooks.md` covers incident workflows and escalation drills.
* `performance_validation.md` defines release-facing performance evidence.
