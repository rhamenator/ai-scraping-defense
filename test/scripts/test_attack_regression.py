from scripts.security import attack_regression


def test_validate_base_url_rejects_missing_scheme():
    try:
        attack_regression._validate_base_url("localhost:8080")
    except ValueError as exc:
        assert "http://" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected ValueError")


def test_missing_security_headers_reports_absent_headers():
    missing = attack_regression._missing_security_headers(
        {
            "x-frame-options": "DENY",
            "referrer-policy": "no-referrer",
        }
    )

    assert "content-security-policy" in missing
    assert "permissions-policy" in missing
    assert "x-content-type-options" in missing


def test_is_https_redirect_requires_https_location():
    assert attack_regression._is_https_redirect(
        307, {"location": "https://example.test/path"}
    )
    assert not attack_regression._is_https_redirect(
        307, {"location": "http://example.test/path"}
    )
    assert not attack_regression._is_https_redirect(
        200, {"location": "https://example.test/path"}
    )


def test_prompt_rate_limit_ok_requires_success_before_429():
    assert attack_regression._prompt_rate_limit_ok([200, 200, 200, 429])
    assert not attack_regression._prompt_rate_limit_ok([429])
    assert not attack_regression._prompt_rate_limit_ok([200, 500, 429])
    assert not attack_regression._prompt_rate_limit_ok([200, 401, 429])
