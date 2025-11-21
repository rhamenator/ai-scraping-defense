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



## Metrics and Traces

* **Prometheus** – Scrape `/metrics` and import `monitoring/prometheus.yml` into
  your Prometheus server.  Grafana dashboards can be built on top of the
  standard HTTP metrics.
* **Traces** – Fetch recent spans via `/observability/traces?limit=200`.  The
  payload is JSON and can be pushed to Tempo, Jaeger, or any trace store.  The
  buffer size is configurable via the `OBS_TRACE_HISTORY` environment variable
  (defaults to 512).

## Security Metrics and KPIs

The AI Scraping Defense platform exposes comprehensive security metrics through
Prometheus to enable real-time monitoring of the security posture.

### Security Metric Categories

#### Attack Detection and Prevention
* `security_attacks_blocked_total` – Counter of blocked attacks by type and severity
* `security_threats_detected_total` – Counter of detected threats by type and source
* `security_threat_score_distribution` – Histogram of threat severity scores
* `security_attack_score_distribution` – Histogram of attack probability scores
* `security_risk_score_distribution` – Histogram of risk assessment scores

#### Authentication and Authorization
* `security_auth_failures_total` – Counter of authentication failures by method and reason
* `security_authz_denials_total` – Counter of authorization denials by resource and action
* `security_active_sessions_current` – Gauge of active authenticated sessions

#### Rate Limiting and Abuse Prevention
* `security_rate_limit_violations_total` – Counter of rate limit violations by endpoint
* `security_captcha_successes_total` / `security_captcha_failures_total` – CAPTCHA results
* `security_honeypot_hits_total` – Counter of honeypot trap activations
* `security_suspicious_patterns_total` – Counter of suspicious activity patterns

#### Security Operations
* `security_incident_escalations_total` – Counter of escalated security incidents
* `security_ip_blocks_total` – Counter of blocked IP addresses
* `security_waf_rules_triggered_total` – Counter of WAF rule triggers
* `security_intrusion_attempts_total` – Counter of detected intrusion attempts

#### Detection Performance
* `security_detection_latency_seconds` – Histogram of time from event to detection
* `security_response_time_seconds` – Histogram of time to respond to security events
* `security_mitigation_time_seconds` – Histogram of time to mitigate threats
* `security_mean_time_to_detect_seconds` – Gauge of rolling average MTTD
* `security_mean_time_to_respond_seconds` – Gauge of rolling average MTTR
* `security_mean_time_to_remediate_seconds` – Gauge of rolling average MTTR

#### Detection Quality
* `security_true_positives_total` / `security_false_positives_total` – Detection accuracy
* `security_true_positive_rate_percent` – Gauge of TPR by detection type
* `security_false_positive_rate_percent` – Gauge of FPR by detection type
* `security_anomalies_detected_total` – Counter of detected anomalies

#### Security Posture
* `security_threat_level_current` – Gauge of overall threat level (0-5)
* `security_active_threats_current` – Gauge of active threats by type
* `security_blocked_ips_current` – Gauge of currently blocked IPs
* `security_compliance_score_current` – Gauge of compliance score (0-100)
* `security_vulnerability_count_current` – Gauge of known vulnerabilities by severity
* `security_detection_coverage_percent` – Gauge of attack vector coverage
* `security_response_readiness_score` – Gauge of incident response readiness (0-100)
* `security_alerts_pending_current` – Gauge of pending security alerts

#### Audit and Compliance
* `security_audit_events_total` – Counter of security audit events
* `security_compliance_violations_total` – Counter of compliance violations
* `security_policy_updates_total` – Counter of policy updates
* `security_policy_version_info` – Gauge of active policy versions

### Security KPIs and Scorecards

The platform provides programmatic access to calculated security KPIs through
the `src.security.security_metrics` module:

```python
from src.security import get_security_metrics_collector

collector = get_security_metrics_collector()

# Record security events
collector.record_attack_blocked("sql_injection", "high", score=0.95)
collector.record_threat_detected("bot", "escalation_engine", score=0.87)

# Update gauges
collector.update_threat_level(3)
collector.update_compliance_score("GDPR", 87.5)

# Calculate KPIs
kpis = collector.calculate_kpis(
    threats_detected=150,
    attacks_blocked=142,
    true_positives=135,
    false_positives=7,
    # ... additional parameters
)

# Generate comprehensive scorecard
scorecard = collector.generate_scorecard(kpis)
print(f"Overall Security Score: {scorecard.overall_score:.1f}/100")
print(f"Strengths: {', '.join(scorecard.strengths)}")
print(f"Recommendations: {', '.join(scorecard.recommendations)}")
```

### Security Dashboards

Recommended Grafana dashboard panels for security monitoring:

1. **Threat Overview** – Current threat level, active threats, blocked attacks
2. **Detection Performance** – MTTD, MTTR, detection accuracy (TPR/FPR)
3. **Attack Trends** – Time series of attacks by type and severity
4. **Authentication Health** – Failed logins, session counts, auth success rate
5. **Security Scorecard** – Multi-dimensional security posture visualization
6. **Compliance Status** – Compliance scores, violations, policy versions
7. **Response Readiness** – Pending alerts, vulnerability counts, readiness score

Example PromQL queries:

```promql
# Attack block rate over time
rate(security_attacks_blocked_total[5m])

# Detection accuracy
(security_true_positives_total / (security_true_positives_total + security_false_positives_total)) * 100

# Average detection latency
histogram_quantile(0.95, rate(security_detection_latency_seconds_bucket[5m]))

# Current threat level heatmap
security_threat_level_current

# Compliance score by standard
security_compliance_score_current{compliance_standard=~"GDPR|SOC2|PCI-DSS"}
```

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

1.  Scrape `/metrics` for Prometheus and configure alerting on latency,
    `http_requests_total`, and service-specific counters.
2.  Collect logs with a JSON-aware shipper (Filebeat, Fluent Bit, Vector) and
    correlate using `trace_id`.
3.  Periodically export `/observability/traces` to verify span fidelity and
    ensure end-to-end timing stays within SLO thresholds.
4.  Use the `scripts/operations_toolkit.py` automation to schedule health
    drills that verify logs, metrics, and traces continue to flow during
    failover tests.

## Next Steps

To implement Observability as Code, consider using Terraform providers to automate the deployment and configuration of monitoring infrastructure. This includes:

*   **Terraform Providers:** Explore providers for Prometheus, Grafana, Loki, and Tempo to manage their configurations.
*   **Configuration Versioning:** Store Prometheus rules and Grafana dashboards in version control (e.g., Git) alongside Terraform code.
*   **Dashboard Automation:** Use Terraform to define and deploy Grafana dashboards, ensuring consistency across environments.
*   **Alert Rule Management:** Automate alert rule creation and updates via Terraform, maintaining a declarative approach to monitoring.
*   **Observability Compliance:** Define and enforce observability standards using Terraform policies to ensure services are properly instrumented.

## Service Mesh Integration

To further enhance microservices operations, consider integrating a service mesh like Istio or Linkerd. Service meshes provide features like:

*   **Traffic Management:** Route requests based on version, weight, or other criteria.
*   **Security:** Enforce authentication, authorization, and encryption between services.
*   **Observability:** Gain deeper insights into service behavior with metrics, tracing, and logging.
*   **Resiliency:** Implement retries, circuit breakers, and fault injection to improve service reliability.

```yaml
# Example Istio VirtualService for traffic management
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: ai-service
spec:
  hosts:
  - ai-service
  http:
  - route:
    - destination:
        host: ai-service
        subset: v1
      weight: 90
    - destination:
        host: ai-service
        subset: v2
      weight: 10
```


## Service Governance Automation

Automating service governance involves defining and enforcing policies for service development, deployment, and operation.  This can be achieved through:

*   **Policy-as-Code:** Define policies using tools like Open Policy Agent (OPA) and integrate them into CI/CD pipelines.
*   **API Gateways:** Implement centralized authentication, authorization, and rate limiting at the API gateway.
*   **Service Catalogs:** Maintain a catalog of services with metadata, dependencies, and ownership information.

## Service Dependency Management

Effective dependency management is crucial for microservices.  Consider using tools like:

*   **Dependency Trackers:** Track dependencies and vulnerabilities in your services.
*   **Service Catalogs:** Document dependencies between services.
*   **Contract Testing:** Ensure compatibility between services by testing against defined contracts.

## Microservices Optimization

Optimize microservices for performance, scalability, and cost-efficiency by:

*   **Profiling:** Identify performance bottlenecks using profiling tools.
*   **Caching:** Implement caching strategies to reduce latency and load on backend services.
*   **Autoscaling:** Automatically scale services based on demand.
*   **Resource Limits:** Define resource limits for each service to prevent resource exhaustion.