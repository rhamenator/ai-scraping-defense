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

## Operational Virtual Reality

To enhance operational readiness and team skills, consider implementing operational virtual reality (VR):

*   **VR Training Programs:** Develop VR-based training modules for incident response, disaster recovery, and routine operations. These modules should simulate real-world scenarios to improve decision-making and coordination under pressure.
*   **Virtual Operations Environments:** Create virtual replicas of production environments to test changes, practice deployments, and troubleshoot issues without impacting live systems. Use tools like Unity or Unreal Engine to build realistic simulations.
*   **Immersive Simulation Workflows:** Integrate VR into existing simulation workflows. For example, use VR to visualize capacity management dashboards or walk through incident response procedures.
*   **VR Metrics:** Define and track VR-specific metrics to measure the effectiveness of VR training programs. Examples include time to resolution, accuracy of decisions, and team coordination scores.
*   **VR Culture Development:** Foster a culture that embraces VR as a valuable tool for operational improvement. Encourage experimentation, share best practices, and provide ongoing training to team members.

**Example VR Training Scenario:**

Simulate a DDoS attack in VR. On-call engineers can collaboratively diagnose the attack, apply mitigation strategies (e.g., adjusting rate limits, activating tarpits), and communicate with stakeholders—all within a realistic virtual environment. This will provide practical experience, reduce response times, and improve overall security posture.