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

## Multi-Cloud Runbook Notes

When deploying across providers, confirm these items before go-live:

* **DNS/Ingress**: Ensure the ingress controller matches the provider load
  balancer model and DNS records point to the correct external IP.
* **Storage Classes**: Align PVC storage classes with provider defaults and
  verify RWX/RWO support for each volume.
* **Secrets**: Use provider-native secret managers or sealed secrets; avoid
  local file secrets in production.
* **Network Policies**: Validate CNI support and default deny policies to match
  security expectations.
* **Monitoring**: Confirm Prometheus scraping targets and external endpoints
  are reachable from the provider network.

## Capacity Management

Capacity dashboards in Grafana use the following metrics:

* `cpu_usage_percent` and `memory_usage_bytes` per service instance.
* Request concurrency via `QUEUE_LENGTH` gauges.
* Redis utilisation from custom health check details.

## Event Taxonomy and Routing

Operational events can be published via Redis Pub/Sub when enabled. This is a
lightweight signal path for downstream monitors or automation.

### Channels and Controls

- **Channel**: `operational_events` (default)
- **Enable**: `OPERATIONAL_EVENT_STREAM_ENABLED=true`
- **Redis DB**: `OPERATIONAL_EVENT_REDIS_DB` (default: 0)

### Core Event Types

- `alert_sent`
- `blocklist_sync_completed`
- `blocklist_sync_empty`
- `blocklist_sync_failed`

### Payload Contract

Each event payload includes:

- `event_type` (string)
- `timestamp` (UTC ISO-8601)
- `payload` (object with event-specific fields)

Example payload fields for `alert_sent`:

- `channel` (webhook|slack|smtp)
- `ip`
- `reason`
- `event_type` (optional)

Example payload fields for `blocklist_sync_completed`:

- `source`
- `added`
- `total`
- `url`

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
* Regularly run the comprehensive operations audit to identify areas for
  improvement and track operational maturity. Address findings in the product
  roadmap.

## Operational Resilience Testing

* **Automated Failure Injection**: Implement automated failure injection using tools like Chaos Mesh or LitmusChaos to simulate various failure scenarios (e.g., pod failures, network latency, CPU stress).
* **Resilience Validation Workflows**: Create workflows that automatically validate the system's resilience after failure injection. These workflows should verify that the system recovers within the defined RTO and RPO.
* **Recovery Testing Automation**: Automate the recovery process to ensure that the system can be quickly restored to a functional state after a failure.
* **Resilience Metrics**: Define and track key resilience metrics such as Mean Time To Recovery (MTTR), Mean Time Between Failures (MTBF), and the number of successful and failed recovery attempts.
* **Resilience Optimization**: Continuously optimize the system's resilience based on the results of failure injection tests and the tracked resilience metrics.
* **WAF Integration:** Integrate Web Application Firewall (WAF) to protect against common web exploits and vulnerabilities. Monitor and log WAF events to identify and mitigate potential threats.

## Digital Twin Implementation

This section outlines the steps for implementing an operational digital twin of the AI Scraping Defense platform. The goal is to create a virtual representation of the system that mirrors real-time operations, enabling simulation-based optimization, virtual operations testing, and advanced analytics.

1.  **Real-time Synchronization**: Establish real-time data feeds from production systems into the digital twin. This includes metrics, logs, configuration, and state information. Use tools like Kafka, Fluentd, or Telegraf to collect and stream data.
2.  **Simulation-Based Optimization**: Develop simulation models of key system components (e.g., AI Service, Escalation Engine) that can be used to optimize performance and resource allocation. Integrate simulation tools with the digital twin to test different configurations and predict their impact on the real system.
3.  **Virtual Operations Testing**: Create a virtual environment within the digital twin where operations teams can test changes and procedures before deploying them to production. This includes simulating incident response scenarios, change management processes, and capacity management exercises.
4.  **Digital Twin Analytics**: Implement analytics dashboards and reports that provide insights into system behavior, identify potential issues, and track the impact of changes. Use machine learning techniques to detect anomalies and predict future trends.
5.  **Digital Twin Culture Development**: Foster a culture of collaboration and experimentation around the digital twin. Encourage operations, development, and data science teams to use the digital twin to improve their workflows and decision-making.

   Key metrics to monitor:

    *   Simulation accuracy (comparison of simulated vs. actual system behavior).
    *   Time to resolve incidents (reduction due to improved testing and simulation).
    *   Resource utilization (optimization of CPU, memory, and network resources).
