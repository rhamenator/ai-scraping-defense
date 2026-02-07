# Monitoring Stack

Docker Compose includes a small Prometheus server for metrics collection and a Grafana instance for visualization. Both services are disabled when deploying to Kubernetes unless you enable them explicitly.

Prometheus scrapes the Python microservices every 15 seconds using `monitoring/prometheus.yml`. Grafana exposes dashboards and can be used to build custom views of request rates, response times, and other service metrics.

Every FastAPI service now exposes a shared observability surface:

- `/metrics` – Prometheus metrics including request counters and latency histograms
- `/health` – Aggregated health checks with per-dependency status
- `/observability/traces` – Recent request spans for debugging and export into Tempo/Jaeger
- `/observability/performance/insights` – Performance analytics insights and degradation alerts
- `/observability/performance/predictions` – Performance predictions for capacity planning
- `/observability/performance/history` – Historical performance data with metric filtering
- JSON structured logs containing `service`, `request_id`, `trace_id`, and `span_id`

Import the dashboards in `monitoring/grafana` to visualise the new metrics and
configure Loki/Tempo to ingest logs and traces if desired.

Watchtower runs alongside these containers and automatically checks for new Docker images every minute, restarting services when updates are available. Remove the `watchtower` section from `docker-compose.yaml` if you prefer manual updates.

```env
# excerpt from sample.env
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
```

- **Prometheus UI:** [http://localhost:${PROMETHEUS_PORT:-9090}](http://localhost:9090)
- **Grafana UI:** [http://localhost:${GRAFANA_PORT:-3000}](http://localhost:3000) (default login `admin`/`admin`)

## Performance Analytics Dashboards

The new performance analytics capabilities provide rich data for building
advanced Grafana dashboards:

### Key Metrics for Dashboards

* `performance_baseline_value` – Baseline values for performance comparisons
* `performance_anomaly_score` – Real-time anomaly scores (0-1)
* `performance_trend` – Trend indicators (-1=declining, 0=stable, 1=improving)
* `performance_percentile_seconds` – Percentile distributions (p50, p95, p99)
* `performance_samples_collected_total` – Total samples collected per metric
* `performance_predictions_generated_total` – Prediction generation activity
* `performance_insights_generated_total` – Insights by type (degradation, anomaly)
* `performance_degradation_detected_total` – Detected degradations over time

### Dashboard Examples

**Performance Overview**
- Visualize trends for key metrics across services
- Alert on anomaly scores exceeding thresholds
- Compare current values against baselines

**Capacity Planning**
- Display predictions with confidence intervals
- Forecast resource requirements
- Track prediction accuracy over time

**Incident Response**
- Show recent performance insights
- Correlate degradations with service changes
- Display percentile distributions for latency analysis

## Automation and Compliance with Terraform

To manage the monitoring stack as code and ensure compliance, consider the following steps:

1.  **Terraform Configuration:** Define Prometheus, Grafana, and associated resources (e.g., persistent volumes, network policies) using Terraform. This allows for infrastructure-as-code and repeatable deployments.
2.  **Monitoring Configuration Versioning:** Manage Prometheus configuration files (e.g., `prometheus.yml`, alert rules) and Grafana dashboards in a version control system (e.g., Git). Use Terraform to deploy these configurations from the repository.
3.  **Dashboard Automation:** Implement Grafana dashboard automation by defining dashboards as code using Terraform's Grafana provider. This ensures consistent dashboards across environments including the new performance analytics dashboards.
4.  **Alert Rule Management:** Define alert rules in code and use Terraform to manage and deploy them to Prometheus. This facilitates easy updates and version control for alerts. Consider adding alerts for performance degradation and anomaly detection.
5.  **Observability Compliance:** Use Terraform policies (e.g., HashiCorp Sentinel, Open Policy Agent) to enforce observability standards, such as ensuring all services expose metrics endpoints, performance analytics, and have appropriate alerting configured.
