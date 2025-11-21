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

## Security Chaos Engineering

Security chaos engineering proactively tests the system's resilience to security-
related failures through controlled failure injection and game day exercises.

### Failure Injection Testing

Regularly test system behavior under failure conditions:

- **Redis Unavailability** – Verify rate limiting degrades gracefully when Redis
  is unavailable. Test with `test/security/test_chaos_engineering.py::TestRedisFailureResilience`.
- **Network Failures** – Validate DDoS protection and escalation engine handle
  network timeouts and intermittent connectivity without crashes.
- **Authentication Failures** – Test audit logging continues when authentication
  services are degraded.
- **Cascading Failures** – Simulate multiple simultaneous failures (Redis + network)
  to validate defense-in-depth and fallback mechanisms.

Run failure injection tests:
```bash
pytest test/security/test_chaos_engineering.py -v
```

### Security Game Days

Conduct quarterly security game day exercises to validate incident response:

1. **DDoS Attack Simulation** – Simulate distributed denial-of-service attacks
   from multiple IPs. Verify rate limiting activates, alerts fire, and system
   remains available for legitimate traffic.

2. **Credential Stuffing Drill** – Test authentication rate limiting and account
   lockout mechanisms under automated credential stuffing attempts.

3. **Multi-Vector Attack** – Simulate coordinated attacks across multiple vectors
   (DDoS + credential stuffing + infrastructure failures) to test comprehensive
   defense capabilities.

4. **Incident Recovery Drill** – Practice full incident lifecycle: detection,
   containment, recovery, and validation. Measure MTTR (Mean Time To Recovery).

Run game day scenarios:
```bash
pytest test/security/test_security_gameday.py -v
```

### Resilience Validation

Key resilience requirements validated through chaos testing:

- **Graceful Degradation** – Security controls degrade gracefully rather than
  failing open when dependencies are unavailable.
- **Fallback Mechanisms** – System automatically falls back to secondary mechanisms
  (e.g., local analysis when cloud services unavailable).
- **Recovery Automation** – System self-recovers when transient failures resolve
  without manual intervention.
- **Blast Radius Containment** – Failure in one security component doesn't cascade
  to unrelated components.

### Metrics and Reporting

Track resilience metrics during chaos tests:

- **Failure Rate** – Percentage of operations that fail during injected failures
- **Fallback Activation Rate** – How often fallback mechanisms activate
- **Recovery Time** – Time to restore normal operation after failure resolution
- **Availability During Failures** – System availability percentage during failures

Generate game day reports to track improvements over time and identify weaknesses.

## Continuous Improvement

- Integrate new findings from subsequent security batches by regenerating the
  inventory (`python src/security_audit/inventory.py`).
- Track remediation status in the governance dashboard with owners, due dates,
  and verification artifacts from CI/CD runs.
- Conduct security chaos engineering tests quarterly and after significant changes.
- Update failure scenarios based on production incidents and emerging threats.
