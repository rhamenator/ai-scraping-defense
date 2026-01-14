import io
import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.shared.observability import (
    HealthCheckResult,
    ObservabilitySettings,
    configure_observability,
    register_health_check,
)


def _create_app() -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"status": "ok"}

    return app


def test_metrics_endpoint_available() -> None:
    app = _create_app()
    settings = ObservabilitySettings(service_name="test-service")
    configure_observability(app, settings)

    client = TestClient(app)
    response = client.get(settings.metrics_path)

    assert response.status_code == 200
    assert "http_requests_total" in response.text


def test_health_endpoint_reports_checks_and_status_code() -> None:
    app = _create_app()
    settings = ObservabilitySettings(service_name="health-service")
    configure_observability(app, settings)

    @register_health_check(app, "database")
    async def database_check():
        return HealthCheckResult.degraded({"latency_ms": 128})

    client = TestClient(app)
    response = client.get(settings.health_path)

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["checks"]["database"]["detail"]["latency_ms"] == 128


def test_configure_observability_emits_json_logs_with_trace() -> None:
    app = _create_app()

    @app.get("/log")
    async def log_endpoint():
        logging.getLogger("test-observability").info("custom log")
        return {"status": "ok"}

    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    for handler in original_handlers:
        root_logger.removeHandler(handler)

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    root_logger.addHandler(handler)

    settings = ObservabilitySettings(service_name="logging-service")

    try:
        configure_observability(app, settings)
        client = TestClient(app)
        response = client.get("/log")
        assert response.status_code == 200
    finally:
        root_logger.removeHandler(handler)
        for original in original_handlers:
            root_logger.addHandler(original)

    log_lines = [line for line in stream.getvalue().splitlines() if line]
    assert log_lines, "expected at least one log line"

    entries = [json.loads(line) for line in log_lines]
    handled_entry = next(
        (entry for entry in entries if entry.get("message") == "Handled request"),
        None,
    )
    assert handled_entry is not None, "missing request completion log entry"
    assert handled_entry["service"] == "logging-service"
    assert handled_entry.get("trace_id")
    assert handled_entry.get("request_id")


def test_performance_analytics_endpoints_available() -> None:
    app = _create_app()
    settings = ObservabilitySettings(service_name="test-perf-service")
    configure_observability(app, settings)

    client = TestClient(app)

    # Test insights endpoint
    response = client.get("/observability/performance/insights")
    assert response.status_code == 200
    assert "insights" in response.json()

    # Test predictions endpoint
    response = client.get("/observability/performance/predictions")
    assert response.status_code == 200
    assert "predictions" in response.json()

    # Test history endpoint
    response = client.get("/observability/performance/history")
    assert response.status_code == 200
    assert "history" in response.json()


def test_performance_analytics_records_metrics() -> None:
    from src.shared.observability import PerformanceAnalytics

    analytics = PerformanceAnalytics(service_name="test-service")
    analytics.record_metric("latency", 0.5)
    analytics.record_metric("latency", 0.7)

    history = analytics.get_history(metric_name="latency")
    assert len(history) == 2
    assert history[0]["metric_name"] == "latency"
    assert history[0]["value"] == 0.5


def test_performance_analytics_detects_degradation() -> None:
    from src.shared.observability import PerformanceAnalytics

    analytics = PerformanceAnalytics(service_name="test-service")
    analytics.set_baseline("latency", 0.1)

    # Record a significantly worse value
    analytics.record_metric("latency", 0.2)

    insights = analytics.get_insights()
    assert len(insights) == 1
    assert insights[0]["insight_type"] == "degradation"
    assert "latency" in insights[0]["description"]


def test_performance_analytics_calculates_trend() -> None:
    from src.shared.observability import PerformanceAnalytics

    analytics = PerformanceAnalytics(service_name="test-service")

    # Record increasing values
    for i in range(5):
        analytics.record_metric("latency", 0.1 + i * 0.1)

    trend = analytics.calculate_trend("latency")
    assert trend > 0  # Positive trend (degrading performance)


def test_performance_analytics_generates_predictions() -> None:
    from src.shared.observability import PerformanceAnalytics

    analytics = PerformanceAnalytics(service_name="test-service")
    prediction = analytics.generate_prediction(
        metric_name="latency",
        prediction_type="capacity",
        predicted_value=0.8,
        confidence=0.9,
        forecast_horizon="1h",
    )

    assert prediction.metric_name == "latency"
    assert prediction.predicted_value == 0.8
    assert prediction.confidence == 0.9

    predictions = analytics.get_predictions()
    assert len(predictions) == 1
    assert predictions[0]["prediction_type"] == "capacity"


def test_performance_analytics_with_percentiles() -> None:
    from src.shared.observability import PerformanceAnalytics

    analytics = PerformanceAnalytics(service_name="test-service")
    percentiles = {"p50": 0.1, "p95": 0.5, "p99": 0.9}
    analytics.record_metric("latency", 0.3, percentiles=percentiles)

    history = analytics.get_history(metric_name="latency")
    assert len(history) == 1
    assert history[0]["percentile_p50"] == 0.1
    assert history[0]["percentile_p95"] == 0.5
    assert history[0]["percentile_p99"] == 0.9
