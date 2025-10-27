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
