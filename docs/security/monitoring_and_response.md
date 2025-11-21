# Security Monitoring, Audit Logging, and Incident Response

This runbook operationalizes the controls enumerated in
`security_problems_batch1.json` by defining how they are monitored, logged,
and escalated in production.

## Telemetry and Monitoring

- **Log aggregation** – All services emit JSON-formatted audit events via
  `src/shared/audit.py`. Forward `/app/logs/audit.log` and service-specific logs
  to a centralized SIEM (e.g., Elastic, Splunk). Retain logs for 180 days.
- **Metrics** – Expose FastAPI metrics via `prometheus-client` and scrape
  latency, error rates, and rate-limit violations. Alerts trigger when 5xx rates
  exceed 1% of traffic or rate-limit denials spike for 10 minutes.
- **Network sensors** – Deploy Suricata (`suricata/`) and fail2ban to monitor
  ingress traffic. Subscribe Nginx access logs to the monitoring pipeline.
- **File integrity** – Enable Docker `--read-only` and host-based integrity
  monitors to watch `/app/src`, `/app/logs`, and secret mounts for unexpected
  changes.

## Security Metrics and KPI Tracking

### Core Security KPIs

The platform tracks the following key security performance indicators:

1. **Detection Effectiveness**
   - True Positive Rate (TPR): Target ≥ 95%
   - False Positive Rate (FPR): Target ≤ 5%
   - Detection Accuracy: Target ≥ 90%
   - Mean Time to Detect (MTTD): Target ≤ 60 seconds

2. **Response Performance**
   - Mean Time to Respond (MTTR): Target ≤ 300 seconds (5 minutes)
   - Mean Time to Remediate: Target ≤ 600 seconds (10 minutes)
   - Response Readiness Score: Target ≥ 85/100

3. **Prevention Metrics**
   - Attack Block Rate: Target ≥ 95%
   - Threat Level: Normal range 0-2, elevated 3-4, critical 5
   - IP Block Effectiveness: Monitor block duration and recidivism

4. **Compliance & Posture**
   - Compliance Score: Target ≥ 90/100 for each standard
   - Vulnerability Count: Target = 0 critical, ≤ 5 high severity
   - Detection Coverage: Target ≥ 95% of known attack vectors
   - Policy Currency: All policies updated within last 90 days

### Security Scorecard

A comprehensive security scorecard is generated from multiple dimensions:

- **Overall Score** (0-100): Weighted average of all component scores
  - Detection Score (25%): TPR, FPR, detection accuracy
  - Response Score (25%): MTTD, MTTR, remediation time
  - Prevention Score (20%): Block rate, threat level
  - Compliance Score (15%): Policy adherence, violation rate
  - Readiness Score (15%): Vulnerability count, alert backlog

Target overall security score: ≥ 85/100

### Alerting Thresholds

Configure Prometheus alerts for the following conditions:

```yaml
# Detection degradation
- alert: LowDetectionAccuracy
  expr: security_true_positive_rate_percent < 85
  for: 15m
  severity: warning

# Response time SLA breach
- alert: SlowSecurityResponse
  expr: security_mean_time_to_respond_seconds > 600
  for: 10m
  severity: critical

# Elevated threat level
- alert: ElevatedThreatLevel
  expr: security_threat_level_current >= 4
  for: 5m
  severity: critical

# High false positive rate
- alert: HighFalsePositiveRate
  expr: security_false_positive_rate_percent > 10
  for: 30m
  severity: warning

# Compliance degradation
- alert: ComplianceScoreLow
  expr: security_compliance_score_current < 80
  for: 1h
  severity: warning

# Critical vulnerabilities
- alert: CriticalVulnerabilities
  expr: security_vulnerability_count_current{severity="critical"} > 0
  for: 5m
  severity: critical

# Alert backlog
- alert: SecurityAlertBacklog
  expr: security_alerts_pending_current{severity="high"} > 20
  for: 30m
  severity: warning
```

### Metric Collection

Security events are recorded using the `SecurityMetricsCollector`:

```python
from src.security import get_security_metrics_collector

collector = get_security_metrics_collector()

# Record attack detection and blocking
collector.record_attack_blocked("sql_injection", "high", score=0.95)
collector.record_threat_detected("bot", "escalation_engine", score=0.87)

# Record timing metrics
collector.record_detection_time("pattern_match", 0.8)
collector.record_response_time("block_ip", 2.5)
collector.record_mitigation_time("rate_limit", 5.0)

# Update security posture gauges
collector.update_threat_level(2)
collector.update_blocked_ips("malicious", 47)
collector.update_compliance_score("GDPR", 92.5)

# Update detection effectiveness
collector.update_detection_rates("bot_detection", true_positives=142, false_positives=8)

# Generate KPIs and scorecard
kpis = collector.calculate_kpis(
    threats_detected=150,
    attacks_blocked=142,
    true_positives=135,
    false_positives=7,
    current_threat_level=2,
    compliance_score=92.5,
)
scorecard = collector.generate_scorecard(kpis)
```

## Audit Logging

- **Coverage** – All authentication flows log success/failure events via
  `src/shared/audit.log_event`. Ensure API controllers record user ID, IP, and
  action scope.
- **Protection** – File permissions hardened to `600`. Rotate audit logs daily
  and back up to encrypted object storage with bucket policies enforcing
  write-only access from workloads.
- **Review cadence** – Security operations reviews audit dashboards daily and
  completes weekly anomaly triage. High-risk anomalies trigger incident response.

## Automated Detection Rules

- **Secrets Exposure** – Alert when `scripts/security/run_static_security_checks`
  or CI pipelines detect plaintext secrets in tracked files.
- **Transport Security Drift** – Alert if the Nginx configuration lacks HSTS,
  TLS1.2+, or rate-limit directives (validated by `test/test_security_baselines.py`).
- **Authentication Abuse** – Fire alerts on >5 failed logins per user or
  repeated token validation failures within 10 minutes.
- **API Abuse** – Monitor `/webhook` rate-limit counters and escalate after
  three consecutive denials from unique IPs.

## Incident Response Workflow

1. **Detection** – Alerts or analysts raise incidents in the ticketing system.
2. **Triage** – Duty analyst validates severity, gathers evidence (logs,
   metrics, request samples), and assigns priority.
3. **Containment** – Depending on incident type:
   - Secrets leakage → rotate via `scripts/linux/generate_secrets.sh --update-env`
     and revoke credentials.
   - Transport/auth issues → deploy hotfix through hardened CI workflow.
   - Intrusion → block offending IPs using the escalation engine webhook.
4. **Eradication & Recovery** – Apply patches, redeploy containers, and verify
   with automated security tests (`pytest -k security`, `bandit`, `trivy`).
5. **Post-Incident Review** – Document root cause, control gaps, and follow-up
   actions in the knowledge base. Update detection rules and runbooks.

## Continuous Improvement

- Integrate new findings from subsequent security batches by regenerating the
  inventory (`python src/security_audit/inventory.py`).
- Track remediation status in the governance dashboard with owners, due dates,
  and verification artifacts from CI/CD runs.
