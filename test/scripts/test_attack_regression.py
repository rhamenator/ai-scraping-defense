import json

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


def test_main_emits_json_and_succeeds(monkeypatch, capsys):
    responses = [
        (308, {"location": "https://edge.test/"}, b""),
        (
            200,
            {
                "content-security-policy": "default-src 'self'",
                "permissions-policy": "geolocation=()",
                "referrer-policy": "no-referrer",
                "x-content-type-options": "nosniff",
                "x-frame-options": "DENY",
            },
            b"",
        ),
        (308, {"location": "https://admin.test/observability/health"}, b""),
        (431, {}, b""),
        (413, {}, b""),
        (200, {}, b""),
        (200, {}, b""),
        (429, {}, b""),
    ]

    def fake_request(*_args, **_kwargs):
        return responses.pop(0)

    monkeypatch.setattr(attack_regression, "_request", fake_request)

    rc = attack_regression.main(
        [
            "--nginx-http-base",
            "http://edge.test",
            "--nginx-https-base",
            "https://edge.test",
            "--admin-ui-base",
            "http://admin.test",
            "--prompt-router-base",
            "http://prompt.test",
            "--prompt-shared-secret",
            "shared-secret",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert rc == 0
    assert captured.err == ""
    assert payload["failures"] == []
    assert [check["name"] for check in payload["checks"]] == [
        "nginx_https_redirect",
        "nginx_security_headers",
        "admin_ui_spoofed_forwarded_proto_redirect",
        "admin_ui_large_header_rejected",
        "admin_ui_large_body_rejected",
        "prompt_router_rate_limit",
    ]
    assert all(check["ok"] for check in payload["checks"])


def test_main_reports_invalid_input_to_stderr(capsys):
    rc = attack_regression.main(
        [
            "--nginx-http-base",
            "edge.test",
            "--nginx-https-base",
            "https://edge.test",
            "--admin-ui-base",
            "http://admin.test",
        ]
    )

    captured = capsys.readouterr()

    assert rc == 2
    assert captured.out == ""
    assert "[attack-regression] invalid input:" in captured.err


def test_main_text_output_reports_failures(monkeypatch, capsys):
    responses = [
        (200, {"location": "http://edge.test/"}, b""),
        (200, {}, b""),
        (200, {"location": "http://admin.test/observability/health"}, b""),
        (200, {}, b""),
        (200, {}, b""),
    ]

    def fake_request(*_args, **_kwargs):
        return responses.pop(0)

    monkeypatch.setattr(attack_regression, "_request", fake_request)

    rc = attack_regression.main(
        [
            "--nginx-http-base",
            "http://edge.test",
            "--nginx-https-base",
            "https://edge.test",
            "--admin-ui-base",
            "http://admin.test",
        ]
    )

    captured = capsys.readouterr()

    assert rc == 2
    assert "- FAIL: nginx_https_redirect" in captured.out
    assert "- FAIL: nginx_security_headers" in captured.out
    assert "- FAIL: admin_ui_spoofed_forwarded_proto_redirect" in captured.out
    assert "- FAIL: admin_ui_large_header_rejected" in captured.out
    assert "- FAIL: admin_ui_large_body_rejected" in captured.out
    assert "[attack-regression] failures:" in captured.err
