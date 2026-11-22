from scripts.check_nginx_exposure import DISALLOWED


def test_nginx_exposure_guard_rejects_affected_protocols_and_modules():
    for directive in (
        "listen 443 ssl http2;",
        "http2 on;",
        "http3 on;",
        "listen 443 quic;",
        "mirror /mirror;",
        "ssi on;",
        "mail {",
        "ssl_protocols TLSv1.2 TLSv1.3;",
    ):
        assert DISALLOWED.search(directive), directive


def test_nginx_exposure_guard_accepts_temporary_safe_baseline():
    for directive in ("listen 443 ssl;", "http2 off;", "ssl_protocols TLSv1.2;"):
        assert not DISALLOWED.search(directive), directive
