"""Observability utilities shared across microservices.

This module centralises logging, metrics, tracing, and health
check registration so that every FastAPI service exposes a
consistent operational surface area.  It intentionally keeps the
implementation lightweight (no hard dependency on OpenTelemetry)
so it can run in constrained environments while still emitting
structured data that external collectors can scrape.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from .metrics import (
    PERFORMANCE_ANOMALY_SCORE,
    PERFORMANCE_BASELINE,
    PERFORMANCE_DEGRADATION_DETECTED,
    PERFORMANCE_INSIGHTS_GENERATED,
    PERFORMANCE_PERCENTILE,
    PERFORMANCE_PREDICTIONS_GENERATED,
    PERFORMANCE_SAMPLES_COLLECTED,
    PERFORMANCE_TREND,
    REQUEST_LATENCY,
    get_metrics,
    record_request,
)

HealthCallable = Callable[[], Awaitable["HealthCheckResult"] | "HealthCheckResult"]


_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
_current_span_ctx: ContextVar["SpanContext" | None] = ContextVar(
    "span_context", default=None
)
_current_state_ctx: ContextVar["ObservabilityState" | None] = ContextVar(
    "observability_state", default=None
)


def _now() -> float:
    return time.perf_counter()


@dataclass
class HealthCheckResult:
    """Return value for health check callables."""

    status: str
    detail: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def healthy(cls, detail: Optional[dict[str, Any]] = None) -> "HealthCheckResult":
        return cls(status="ok", detail=detail or {})

    @classmethod
    def degraded(cls, detail: Optional[dict[str, Any]] = None) -> "HealthCheckResult":
        return cls(status="degraded", detail=detail or {})

    @classmethod
    def unhealthy(cls, detail: Optional[dict[str, Any]] = None) -> "HealthCheckResult":
        return cls(status="error", detail=detail or {})


@dataclass
class HealthCheck:
    name: str
    check: HealthCallable
    critical: bool = True


@dataclass
class SpanContext:
    trace_id: str
    span_id: str
    name: str
    attributes: dict[str, Any]
    start_time: float
    parent_id: str | None = None
    status: str = "ok"
    duration: float | None = None

    def to_json(self) -> dict[str, Any]:
        payload = {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_id,
            "name": self.name,
            "status": self.status,
            "start_time": datetime.fromtimestamp(
                self.start_time, tz=timezone.utc
            ).isoformat(),
            "attributes": self.attributes,
        }
        if self.duration is not None:
            payload["duration_seconds"] = self.duration
        return payload


class TraceBuffer:
    """Keep a rolling history of recent spans for debugging."""

    def __init__(self, maxlen: int = 512) -> None:
        self._spans: deque[dict[str, Any]] = deque(maxlen=maxlen)

    def append(self, span: SpanContext) -> None:
        self._spans.append(span.to_json())

    def latest(self, limit: int | None = None) -> list[dict[str, Any]]:
        if limit is None:
            return list(self._spans)
        if limit <= 0:
            return []
        return list(self._spans)[-limit:]


class JsonFormatter(logging.Formatter):
    """Emit JSON log records with trace/request correlation."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:  # pragma: no cover - format
        payload = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service": self._service_name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or get_request_id()
        if request_id:
            payload["request_id"] = request_id
        span = get_current_span()
        if span:
            payload.setdefault("trace_id", span.trace_id)
            payload.setdefault("span_id", span.span_id)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for key, value in getattr(record, "extra_fields", {}).items():
            payload[key] = value
        return json.dumps(payload, default=str)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        span = get_current_span()
        if span:
            record.trace_id = span.trace_id
            record.span_id = span.span_id
        return True


@dataclass
class ObservabilitySettings:
    service_name: str | None = None
    metrics_path: str = "/metrics"
    traces_path: str = "/observability/traces"
    health_path: str = "/health"
    request_id_header: str = "X-Request-ID"
    trace_id_header: str = "X-Trace-ID"
    span_id_header: str = "X-Span-ID"
    trace_history: int = 512
    log_level: str | None = None


class ObservabilityState:
    def __init__(self, settings: ObservabilitySettings) -> None:
        self.settings = settings
        self.health_checks: list[HealthCheck] = []
        self.trace_buffer = TraceBuffer(maxlen=settings.trace_history)

    def add_health_check(self, health_check: HealthCheck) -> None:
        self.health_checks.append(health_check)

    def record_span(self, span: SpanContext) -> None:
        self.trace_buffer.append(span)


def _get_or_create_state(app: FastAPI) -> ObservabilityState:
    state = getattr(app.state, "observability", None)
    if state is None:
        raise RuntimeError("Observability not configured for this app")
    return state


def get_request_id() -> str | None:
    return _request_id_ctx.get()


def get_current_span() -> SpanContext | None:
    return _current_span_ctx.get()


class trace_span:  # pylint: disable=invalid-name
    """Context manager for manual span creation."""

    def __init__(
        self, name: str, *, attributes: Optional[dict[str, Any]] = None
    ) -> None:
        self._name = name
        self._attributes = attributes or {}
        self._span: SpanContext | None = None
        self._span_token = None

    def __enter__(self) -> SpanContext:
        parent = get_current_span()
        trace_id = parent.trace_id if parent else uuid.uuid4().hex
        span_id = uuid.uuid4().hex
        span = SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            name=self._name,
            attributes=dict(self._attributes),
            start_time=time.time(),
            parent_id=parent.span_id if parent else None,
        )
        self._span = span
        self._span_token = _current_span_ctx.set(span)
        return span

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - context glue
        span = self._span
        if span is None:
            return
        if exc:
            span.status = "error"
            span.attributes.setdefault("error", repr(exc))
        span.duration = time.time() - span.start_time
        state = _current_state_ctx.get()
        if state is not None:
            state.record_span(span)
        if self._span_token is not None:
            _current_span_ctx.reset(self._span_token)
        self._span = None


def configure_logging(settings: ObservabilitySettings) -> None:
    service_name = settings.service_name or "service"
    root_logger = logging.getLogger()
    level_name = (settings.log_level or os.getenv("LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter(service_name))
        handler.addFilter(RequestContextFilter())
        root_logger.addHandler(handler)
    else:
        for handler in root_logger.handlers:
            handler.addFilter(RequestContextFilter())
            formatter = getattr(handler, "formatter", None)
            if isinstance(formatter, JsonFormatter):
                continue
            handler.setFormatter(JsonFormatter(service_name))
    root_logger.setLevel(level)
    for handler in root_logger.handlers:
        handler.setLevel(level)


async def _run_health_check(check: HealthCheck) -> HealthCheckResult:
    result = check.check()
    if isinstance(result, Awaitable):
        result = await result
    return result


def _determine_status(results: list[tuple[HealthCheck, HealthCheckResult]]) -> str:
    overall = "ok"
    for check, result in results:
        if result.status == "error" and check.critical:
            return "error"
        if result.status != "ok" and overall == "ok":
            overall = "degraded"
    return overall


def _add_metrics_route(app: FastAPI, settings: ObservabilitySettings) -> None:
    if any(getattr(route, "path", None) == settings.metrics_path for route in app.routes):
        return

    @app.get(settings.metrics_path, include_in_schema=False)
    async def metrics_endpoint() -> PlainTextResponse:  # pragma: no cover - simple IO
        data = get_metrics()
        return PlainTextResponse(data, media_type="text/plain; version=0.0.4")


def _add_traces_route(app: FastAPI, settings: ObservabilitySettings) -> None:
    if any(getattr(route, "path", None) == settings.traces_path for route in app.routes):
        return

    @app.get(settings.traces_path, include_in_schema=False)
    async def recent_traces(limit: int = 100) -> JSONResponse:
        state = _get_or_create_state(app)
        return JSONResponse({"traces": state.trace_buffer.latest(limit)})


def _add_health_route(app: FastAPI, settings: ObservabilitySettings) -> None:
    if any(getattr(route, "path", None) == settings.health_path for route in app.routes):
        return

    @app.get(settings.health_path, include_in_schema=False)
    async def health_endpoint() -> JSONResponse:
        state = _get_or_create_state(app)
        checks = state.health_checks or [
            HealthCheck(name="startup", check=lambda: HealthCheckResult.healthy())
        ]
        results: list[tuple[HealthCheck, HealthCheckResult]] = []
        for check in checks:
            try:
                result = await _run_health_check(check)
            except Exception as exc:  # pragma: no cover - defensive
                logging.getLogger(__name__).exception(
                    "Health check '%s' failed", check.name, extra={"extra_fields": {"error": str(exc)}}
                )
                result = HealthCheckResult.unhealthy({"error": str(exc)})
            results.append((check, result))
        status = _determine_status(results)
        payload = {
            "status": status,
            "service": settings.service_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": {
                check.name: {"status": result.status, "detail": result.detail}
                for check, result in results
            },
        }
        status_code = 200 if status == "ok" else 503
        return JSONResponse(payload, status_code=status_code)


def configure_observability(
    app: FastAPI, settings: ObservabilitySettings | None = None
) -> ObservabilitySettings:
    settings = settings or ObservabilitySettings()
    settings.service_name = (
        settings.service_name
        or app.title
        or os.getenv("SERVICE_NAME")
        or "ai-scraping-defense-service"
    )
    configure_logging(settings)
    state = ObservabilityState(settings)
    app.state.observability = state

    # Initialize performance analytics
    analytics = PerformanceAnalytics(service_name=settings.service_name)
    app.state.performance_analytics = analytics

    _add_metrics_route(app, settings)
    _add_traces_route(app, settings)
    _add_health_route(app, settings)
    _add_performance_analytics_routes(app, settings)

    logger = logging.getLogger(settings.service_name)

    @app.middleware("http")
    async def observability_middleware(request: Request, call_next):
        request_id = (
            request.headers.get(settings.request_id_header)
            or str(uuid.uuid4())
        )
        trace_id = request.headers.get(settings.trace_id_header) or request_id
        span_id = request.headers.get(settings.span_id_header) or uuid.uuid4().hex
        endpoint = getattr(request.scope.get("route"), "path", request.url.path)
        start = _now()
        token_request = _request_id_ctx.set(request_id)
        span = SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            name=f"http {request.method} {endpoint}",
            attributes={
                "method": request.method,
                "path": endpoint,
                "client": request.client.host if request.client else None,
            },
            start_time=time.time(),
        )
        token_span = _current_span_ctx.set(span)
        token_state = _current_state_ctx.set(state)
        status_code = 500
        response: Response | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            span.status = "error"
            span.attributes.setdefault("error", repr(exc))
            logger.exception(
                "Unhandled exception during request",
                extra={"extra_fields": {"path": endpoint, "method": request.method}},
            )
            raise
        finally:
            duration = _now() - start
            span.duration = duration
            state.record_span(span)
            record_request(request.method, endpoint, status_code)
            REQUEST_LATENCY.labels(method=request.method, endpoint=endpoint).observe(duration)
            logger.info(
                "Handled request",
                extra={
                    "extra_fields": {
                        "method": request.method,
                        "path": endpoint,
                        "status_code": status_code,
                        "duration_seconds": round(duration, 6),
                        "client_ip": request.client.host if request.client else None,
                    }
                },
            )
            if response is not None:
                response.headers.setdefault(settings.request_id_header, request_id)
                response.headers.setdefault(settings.trace_id_header, trace_id)
                response.headers.setdefault(settings.span_id_header, span_id)
            _current_span_ctx.reset(token_span)
            _request_id_ctx.reset(token_request)
            _current_state_ctx.reset(token_state)
        return response

    return settings


def register_health_check(
    app: FastAPI,
    name: str,
    *,
    critical: bool = True,
) -> Callable[[HealthCallable], HealthCallable]:
    state = _get_or_create_state(app)

    def decorator(func: HealthCallable) -> HealthCallable:
        state.add_health_check(HealthCheck(name=name, check=func, critical=critical))
        return func

    return decorator


@dataclass
class PerformanceMetrics:
    """Performance metrics snapshot for analytics."""

    metric_name: str
    service: str
    value: float
    timestamp: float
    percentile_p50: float | None = None
    percentile_p95: float | None = None
    percentile_p99: float | None = None

    def to_json(self) -> dict[str, Any]:
        payload = {
            "metric_name": self.metric_name,
            "service": self.service,
            "value": self.value,
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
        }
        if self.percentile_p50 is not None:
            payload["percentile_p50"] = self.percentile_p50
        if self.percentile_p95 is not None:
            payload["percentile_p95"] = self.percentile_p95
        if self.percentile_p99 is not None:
            payload["percentile_p99"] = self.percentile_p99
        return payload


@dataclass
class PerformanceInsight:
    """Performance insight derived from analytics."""

    insight_type: str
    service: str
    metric_name: str
    description: str
    severity: str
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "insight_type": self.insight_type,
            "service": self.service,
            "metric_name": self.metric_name,
            "description": self.description,
            "severity": self.severity,
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class PerformancePrediction:
    """Performance prediction for capacity planning."""

    prediction_type: str
    service: str
    metric_name: str
    predicted_value: float
    confidence: float
    forecast_horizon: str
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "prediction_type": self.prediction_type,
            "service": self.service,
            "metric_name": self.metric_name,
            "predicted_value": self.predicted_value,
            "confidence": self.confidence,
            "forecast_horizon": self.forecast_horizon,
            "timestamp": datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat(),
            "metadata": self.metadata,
        }


class PerformanceAnalytics:
    """Track and analyze performance metrics over time."""

    def __init__(self, service_name: str, history_size: int = 1000) -> None:
        self.service_name = service_name
        self._history: deque[PerformanceMetrics] = deque(maxlen=history_size)
        self._baselines: dict[str, float] = {}
        self._insights: deque[PerformanceInsight] = deque(maxlen=100)
        self._predictions: deque[PerformancePrediction] = deque(maxlen=50)

    def record_metric(
        self,
        metric_name: str,
        value: float,
        percentiles: Optional[dict[str, float]] = None,
    ) -> None:
        """Record a performance metric sample."""
        timestamp = time.time()
        metrics = PerformanceMetrics(
            metric_name=metric_name,
            service=self.service_name,
            value=value,
            timestamp=timestamp,
            percentile_p50=percentiles.get("p50") if percentiles else None,
            percentile_p95=percentiles.get("p95") if percentiles else None,
            percentile_p99=percentiles.get("p99") if percentiles else None,
        )
        self._history.append(metrics)
        PERFORMANCE_SAMPLES_COLLECTED.labels(
            metric_name=metric_name, service=self.service_name
        ).inc()

        # Record percentiles
        if percentiles:
            for percentile_name, percentile_value in percentiles.items():
                PERFORMANCE_PERCENTILE.labels(
                    metric_name=f"{metric_name}_{percentile_name}",
                    service=self.service_name,
                ).observe(percentile_value)

        # Check for anomalies
        self._check_for_anomalies(metric_name, value)

    def set_baseline(self, metric_name: str, baseline_value: float) -> None:
        """Set performance baseline for a metric."""
        self._baselines[metric_name] = baseline_value
        PERFORMANCE_BASELINE.labels(
            metric_name=metric_name, service=self.service_name
        ).set(baseline_value)

    def _check_for_anomalies(self, metric_name: str, value: float) -> None:
        """Check if current value deviates from baseline."""
        baseline = self._baselines.get(metric_name)
        if baseline is None:
            return

        # Simple threshold-based anomaly detection
        deviation = abs(value - baseline) / baseline if baseline > 0 else 0
        anomaly_score = min(deviation, 1.0)

        PERFORMANCE_ANOMALY_SCORE.labels(
            metric_name=metric_name, service=self.service_name
        ).set(anomaly_score)

        # Detect degradation (value increased by more than 50%)
        if value > baseline * 1.5:
            PERFORMANCE_DEGRADATION_DETECTED.labels(
                metric_name=metric_name, service=self.service_name
            ).inc()
            insight = PerformanceInsight(
                insight_type="degradation",
                service=self.service_name,
                metric_name=metric_name,
                description=f"Performance degradation detected: {metric_name} increased from {baseline:.3f} to {value:.3f}",
                severity="warning",
                timestamp=time.time(),
                metadata={"baseline": baseline, "current": value, "deviation": deviation},
            )
            self._insights.append(insight)
            PERFORMANCE_INSIGHTS_GENERATED.labels(
                insight_type="degradation", service=self.service_name
            ).inc()

    def calculate_trend(self, metric_name: str, window_size: int = 10) -> float:
        """Calculate performance trend for a metric."""
        recent = [
            m.value
            for m in list(self._history)[-window_size:]
            if m.metric_name == metric_name
        ]
        if len(recent) < 2:
            return 0.0

        # Simple linear regression slope
        n = len(recent)
        x_mean = (n - 1) / 2
        y_mean = sum(recent) / n
        numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(recent))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0

        slope = numerator / denominator
        # Normalize to -1, 0, 1
        trend = max(-1.0, min(1.0, slope * 10))

        PERFORMANCE_TREND.labels(metric_name=metric_name, service=self.service_name).set(
            trend
        )
        return trend

    def generate_prediction(
        self,
        metric_name: str,
        prediction_type: str,
        predicted_value: float,
        confidence: float,
        forecast_horizon: str = "1h",
    ) -> PerformancePrediction:
        """Generate a performance prediction."""
        prediction = PerformancePrediction(
            prediction_type=prediction_type,
            service=self.service_name,
            metric_name=metric_name,
            predicted_value=predicted_value,
            confidence=confidence,
            forecast_horizon=forecast_horizon,
            timestamp=time.time(),
        )
        self._predictions.append(prediction)
        PERFORMANCE_PREDICTIONS_GENERATED.labels(
            prediction_type=prediction_type, service=self.service_name
        ).inc()
        return prediction

    def get_insights(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent performance insights."""
        return [insight.to_json() for insight in list(self._insights)[-limit:]]

    def get_predictions(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent performance predictions."""
        return [pred.to_json() for pred in list(self._predictions)[-limit:]]

    def get_history(
        self, metric_name: Optional[str] = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get performance history."""
        history = list(self._history)[-limit:]
        if metric_name:
            history = [m for m in history if m.metric_name == metric_name]
        return [m.to_json() for m in history]


_performance_analytics_ctx: ContextVar[PerformanceAnalytics | None] = ContextVar(
    "performance_analytics", default=None
)


def get_performance_analytics() -> PerformanceAnalytics | None:
    """Get the current performance analytics instance."""
    return _performance_analytics_ctx.get()


def _add_performance_analytics_routes(
    app: FastAPI, settings: ObservabilitySettings
) -> None:
    """Add performance analytics endpoints."""
    analytics_path = "/observability/performance"

    if any(getattr(route, "path", None) == analytics_path for route in app.routes):
        return

    @app.get(f"{analytics_path}/insights", include_in_schema=False)
    async def performance_insights(limit: int = 20) -> JSONResponse:
        analytics = get_performance_analytics()
        if analytics is None:
            return JSONResponse({"insights": []})
        return JSONResponse({"insights": analytics.get_insights(limit)})

    @app.get(f"{analytics_path}/predictions", include_in_schema=False)
    async def performance_predictions(limit: int = 10) -> JSONResponse:
        analytics = get_performance_analytics()
        if analytics is None:
            return JSONResponse({"predictions": []})
        return JSONResponse({"predictions": analytics.get_predictions(limit)})

    @app.get(f"{analytics_path}/history", include_in_schema=False)
    async def performance_history(
        metric_name: Optional[str] = None, limit: int = 100
    ) -> JSONResponse:
        analytics = get_performance_analytics()
        if analytics is None:
            return JSONResponse({"history": []})
        return JSONResponse(
            {"history": analytics.get_history(metric_name=metric_name, limit=limit)}
        )


__all__ = [
    "configure_observability",
    "ObservabilitySettings",
    "register_health_check",
    "HealthCheckResult",
    "trace_span",
    "get_request_id",
    "get_current_span",
]
