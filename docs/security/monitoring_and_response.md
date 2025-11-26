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

## Secret Management and Rotation

The system now includes comprehensive HashiCorp Vault integration for enhanced secret management:

- **Automated Rotation** – Secret rotation service (`src/security/secret_rotation.py`)
  automatically rotates secrets based on configurable policies (default: 90 days for
  most secrets, 180 days for system seed).
- **Lifecycle Management** – Track secret age, version count, and compliance status.
  Automatic cleanup of old versions (keeps latest 10 by default).
- **Compliance Monitoring** – Real-time compliance checks with Prometheus metrics:
  - `vault_secret_age_days` – Current age of each secret
  - `vault_secret_compliance_score` – Compliance score (0-100)
  - `vault_secret_rotation_total` – Count of successful/failed rotations
  - `vault_secret_version_count` – Number of versions per secret
- **Audit Logging** – All secret access and rotation operations are logged to
  `audit.log` with timestamps, paths, and operation status.

### Manual Secret Rotation

When immediate rotation is required (e.g., suspected compromise):

```bash
# Generate new secrets locally
./scripts/generate_secrets.sh --update-env --export-path /tmp/secrets.json

# Or store directly in Vault
./scripts/generate_secrets.sh --vault \
  --vault-addr https://vault.example.com:8200 \
  --vault-token $VAULT_TOKEN

# Using Python rotation service
python -c "
from src.security.secret_rotation import SecretRotationService, SecretRotationPolicy
service = SecretRotationService()
policy = SecretRotationPolicy(
    name='redis_password',
    path='database/redis',
    key_name='password',
    rotation_period_days=90
)
result = service.rotate_secret(policy, force=True)
print(result)
"
```

### Compliance Reports

Generate compliance reports for all secrets:

```bash
python -c "
from src.security.secret_compliance import SecretComplianceMonitor, create_default_compliance_policies
monitor = SecretComplianceMonitor()
report = monitor.generate_compliance_report(create_default_compliance_policies())
print(f'Compliant: {report[\"compliant\"]}/{report[\"total_secrets\"]}')
print(f'Average Score: {report[\"average_score\"]:.1f}')
"
```

## Incident Response Workflow

1. **Detection** – Alerts or analysts raise incidents in the ticketing system.
2. **Triage** – Duty analyst validates severity, gathers evidence (logs,
   metrics, request samples), and assigns priority.
3. **Containment** – Depending on incident type:
   - **Secrets leakage** → 
     - Immediately rotate via `./scripts/generate_secrets.sh --vault --update-env`
     - If using Vault, rotation is tracked and versioned automatically
     - Revoke old credentials in external systems (databases, APIs)
     - Check audit logs for unauthorized access: `grep "secret_access" /app/logs/audit.log`
   - **Transport/auth issues** → deploy hotfix through hardened CI workflow.
   - **Intrusion** → block offending IPs using the escalation engine webhook.
4. **Eradication & Recovery** – Apply patches, redeploy containers, and verify
   with automated security tests (`pytest -k security`, `bandit`, `trivy`).
5. **Post-Incident Review** – Document root cause, control gaps, and follow-up
   actions in the knowledge base. Update detection rules and runbooks.

## Continuous Improvement

- Integrate new findings from subsequent security batches by regenerating the
  inventory (`python src/security_audit/inventory.py`).
- Track remediation status in the governance dashboard with owners, due dates,
  and verification artifacts from CI/CD runs.