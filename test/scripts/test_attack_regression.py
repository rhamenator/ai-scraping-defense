import json

from scripts.security import attack_regression


def test_validate_base_url_rejects_missing_scheme():
    try:
        attack_regression._validate_base_url("localhost:8080")
    except ValueError as exc:
        assert "http://" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected ValueError")


def test_validate_allowed_hosts_requires_explicit_allowlist():
    try:
        attack_regression._validate_allowed_hosts(["http://127.0.0.1:8080"], [])
    except ValueError as exc:
        assert "--allow-host" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected ValueError")


def test_validate_allowed_hosts_rejects_unknown_target():
    denied = attack_regression._validate_allowed_hosts(
        ["http://127.0.0.1:8080", "https://edge.test"],
        ["127.0.0.1"],
    )

    assert denied == ["edge.test"]


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


def test_main_emits_json_and_succeeds(monkeypatch, capsys, tmp_path):
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
        (401, {}, b""),
        (431, {}, b""),
        (413, {}, b""),
        (200, {}, b""),
        (200, {}, b""),
        (429, {}, b""),
    ]
    output_path = tmp_path / "attack-regression.json"

    def fake_request(*_args, **_kwargs):
        return responses.pop(0)

    monkeypatch.setattr(attack_regression, "_request", fake_request)
    monkeypatch.setattr(
        attack_regression,
        "_websocket_handshake_status",
        lambda *_args, **_kwargs: 403,
    )

    rc = attack_regression.main(
        [
            "--profile",
            "compose-v1",
            "--nginx-http-base",
            "http://127.0.0.1:8088",
            "--nginx-https-base",
            "https://127.0.0.1:8443",
            "--admin-ui-base",
            "http://127.0.0.1:5002",
            "--prompt-router-base",
            "http://127.0.0.1:8009",
            "--prompt-shared-secret",
            "shared-secret",
            "--allow-host",
            "127.0.0.1",
            "--output-path",
            str(output_path),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    persisted = json.loads(output_path.read_text())

    assert rc == 0
    assert captured.err == ""
    assert payload["failures"] == []
    assert payload["profile"] == {
        "name": "compose-v1",
        "mode": "compose",
        "version": 1,
    }
    assert payload["request_budget"] == {"limit": 12, "used": 12}
    assert persisted == payload
    assert [check["name"] for check in payload["checks"]] == [
        "nginx_https_redirect",
        "nginx_security_headers",
        "admin_ui_spoofed_forwarded_proto_redirect",
        "admin_ui_missing_auth_rejected",
        "admin_ui_websocket_missing_auth_rejected",
        "admin_ui_large_header_rejected",
        "admin_ui_large_body_rejected",
        "prompt_router_rate_limit",
    ]
    assert all(check["ok"] for check in payload["checks"])


def test_main_reports_invalid_input_to_stderr(capsys):
    rc = attack_regression.main(
        [
            "--profile",
            "compose-v1",
            "--nginx-http-base",
            "edge.test",
            "--nginx-https-base",
            "https://127.0.0.1:8443",
            "--admin-ui-base",
            "http://127.0.0.1:5002",
            "--allow-host",
            "127.0.0.1",
        ]
    )

    captured = capsys.readouterr()

    assert rc == 2
    assert captured.out == ""
    assert "[attack-regression] invalid input:" in captured.err


def test_main_rejects_non_allowlisted_host(capsys):
    rc = attack_regression.main(
        [
            "--profile",
            "compose-v1",
            "--nginx-http-base",
            "http://127.0.0.1:8088",
            "--nginx-https-base",
            "https://127.0.0.1:8443",
            "--admin-ui-base",
            "http://127.0.0.1:5002",
            "--allow-host",
            "localhost",
        ]
    )

    captured = capsys.readouterr()

    assert rc == 2
    assert "not allowlisted" in captured.err


def test_main_enforces_request_cap(monkeypatch, capsys):
    def fake_request(*_args, **_kwargs):
        return (200, {}, b"")

    monkeypatch.setattr(attack_regression, "_request", fake_request)
    monkeypatch.setattr(
        attack_regression,
        "_websocket_handshake_status",
        lambda *_args, **_kwargs: 403,
    )

    rc = attack_regression.main(
        [
            "--profile",
            "compose-v1",
            "--nginx-http-base",
            "http://127.0.0.1:8088",
            "--nginx-https-base",
            "https://127.0.0.1:8443",
            "--admin-ui-base",
            "http://127.0.0.1:5002",
            "--prompt-router-base",
            "http://127.0.0.1:8009",
            "--prompt-shared-secret",
            "shared-secret",
            "--allow-host",
            "127.0.0.1",
            "--max-requests",
            "3",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert rc == 2
    assert payload["request_budget"] == {"limit": 3, "used": 3}
    assert "admin_ui_missing_auth_rejected" in payload["failures"]


def test_staging_profile_runs_waf_probe(monkeypatch, capsys):
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
        (401, {}, b""),
        (431, {}, b""),
        (413, {}, b""),
        (403, {}, b""),
    ]

    def fake_request(*_args, **_kwargs):
        return responses.pop(0)

    monkeypatch.setattr(attack_regression, "_request", fake_request)
    monkeypatch.setattr(
        attack_regression,
        "_websocket_handshake_status",
        lambda *_args, **_kwargs: 403,
    )

    rc = attack_regression.main(
        [
            "--profile",
            "staging-v1",
            "--nginx-http-base",
            "http://staging.example.test",
            "--nginx-https-base",
            "https://staging.example.test",
            "--admin-ui-base",
            "https://admin.example.test",
            "--allow-host",
            "staging.example.test",
            "--allow-host",
            "admin.example.test",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["checks"][-1]["name"] == "edge_waf_payload_rejected"
    assert payload["checks"][-1]["ok"] is True
