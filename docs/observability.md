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

python
from src.shared.observability import register_health_check, trace_span

app = create_app(title="Example Service")

@register_health_check(app, "redis")
async def redis_health():
    ...

with trace_span("example.operation", attributes={"foo": "bar"}):
    ...


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

## Operational Data Analytics

To enable operational data analytics:

1.  Import the Grafana dashboards in `monitoring/grafana` to visualize the new data pipeline metrics.
2.  Set up alerts for data pipeline failures and performance degradation based on the new metrics.
