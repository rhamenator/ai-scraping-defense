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
