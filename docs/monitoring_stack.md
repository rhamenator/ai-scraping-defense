# Monitoring Stack

Docker Compose includes a small Prometheus server for metrics collection and a Grafana instance for visualization. Both services are disabled when deploying to Kubernetes unless you enable them explicitly.

Prometheus scrapes the Python microservices every 15 seconds using `monitoring/prometheus.yml`. Grafana exposes dashboards and can be used to build custom views of request rates, response times, and other service metrics.

Watchtower runs alongside these containers and automatically checks for new Docker images every minute, restarting services when updates are available. Remove the `watchtower` section from `docker-compose.yaml` if you prefer manual updates.

```env
# excerpt from sample.env
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
```

- **Prometheus UI:** [http://localhost:${PROMETHEUS_PORT:-9090}](http://localhost:9090)
- **Grafana UI:** [http://localhost:${GRAFANA_PORT:-3000}](http://localhost:3000) (default login `admin`/`admin`)
