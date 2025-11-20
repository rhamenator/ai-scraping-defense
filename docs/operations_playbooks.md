# Operations Playbooks

This document defines the service level objectives (SLOs), incident response
workflows, and capacity management dashboards for the AI Scraping Defense
platform.

## Service Level Objectives

| Service             | SLO                                      | Measurement                            |
|---------------------|------------------------------------------|----------------------------------------|
| Escalation Engine   | 99.9% of requests < 1.5s                 | Prometheus `http_request_duration`     |
| AI Service          | 99.5% webhook latency < 500ms            | Histogram quantiles                    |
| Admin UI            | 99% availability                         | `/health` uptime                       |
| Tarpit API          | Error rate < 0.5%                        | `http_requests_total` vs `errors_total`|
| Cloud Dashboard     | Metrics fanout < 2s                      | `REQUEST_LATENCY` by endpoint          |

SLO dashboards are provided in Grafana.  Alert thresholds are derived from SLOs
with a 5-minute evaluation window.

## Incident Response Workflow

1. **Detection** – Alerts from Prometheus or external monitoring trigger the
   incident process.  PagerDuty routes to the on-call engineer.
2. **Triage** – Within 5 minutes, create an incident ticket, declare severity,
   and assign roles (incident commander, communications, scribe).
3. **Mitigation** – Use the observability stack to identify failing checks,
   apply runbooks (rollback via `scripts/operations_toolkit.py deploy --execute`),
   or failover via the disaster recovery drill.
4. **Communication** – Update Slack `#incident`, customer status page, and
   stakeholders every 15 minutes.
5. **Postmortem** – Within 48 hours, deliver a blameless postmortem with action
   items, SLO impact, and follow-up tasks.

## Change Management

* All production changes must originate from Git pull requests with approved
  reviews and pass CI/CD pipelines.
* `scripts/operations_toolkit.py deploy --execute` is invoked by CI after
  Terraform plan approval and Ansible linting.
* GitOps reconciliation (`scripts/operations_toolkit.py gitops --execute`) runs
  hourly to detect drift.
* Changes are logged to an audit trail (CI artifacts + Git history) satisfying
  compliance requirements.

## Capacity Management

Capacity dashboards in Grafana use the following metrics:

* `cpu_usage_percent` and `memory_usage_bytes` per service instance.
* Request concurrency via `QUEUE_LENGTH` gauges.
* Redis utilisation from custom health check details.

Run the capacity review weekly:

1. Export dashboards as PDF for historical comparison.
2. Forecast 30-day growth using Prometheus recording rules.
3. Raise infrastructure tickets when utilisation exceeds 70% of allocated
   resources for more than 3 consecutive days.

## Continuous Improvement

* Automate incident simulations with `scripts/operations_toolkit.py drill`.
* Expand synthetic monitoring to cover all public endpoints.
* Track error budgets derived from the SLO table and integrate with the product
  roadmap.
* Regularly run the comprehensive operations audit to identify areas for improvement and track operational maturity.  Address findings in the product roadmap.
