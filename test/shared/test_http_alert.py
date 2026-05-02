import pytest

from src.shared import http_alert
from src.shared.http_alert import _safe_endpoint_for_logs


def test_safe_endpoint_for_logs_redacts_path_and_query() -> None:
    url = "https://example.com/services/T00000000/B00000000/SECRETSECRETSECRET"
    safe = _safe_endpoint_for_logs(url)
    origin = safe.split(" ", 1)[0]
    assert origin == "https://example.com", safe
    assert "services" not in safe
    assert "T00000000" not in safe
    assert "SECRET" not in safe
    assert "id=" in safe


def test_safe_endpoint_for_logs_handles_invalid_url() -> None:
    safe = _safe_endpoint_for_logs("not a url")
    assert safe.startswith("<invalid-url>")


@pytest.mark.asyncio
async def test_send_alert_records_delivery_event(monkeypatch) -> None:
    class DummyResponse:
        status_code = 204

        def raise_for_status(self) -> None:
            return None

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def async_post_json(self, *_args, **_kwargs):
            return DummyResponse()

    recorded = []
    monkeypatch.setattr(http_alert, "AsyncHttpClient", lambda **_kwargs: DummyClient())
    monkeypatch.setattr(
        http_alert,
        "_record_delivery_event",
        lambda action, severity, payload: recorded.append((action, severity, payload)),
    )

    sender = http_alert.HttpAlertSender("https://example.com/hooks/secret")
    result = await sender.send_alert({"alert_type": "security", "severity": "high"})

    assert result is True
    assert recorded
    assert recorded[0][0] == "delivered"
