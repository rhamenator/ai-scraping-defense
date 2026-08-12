import hashlib
import hmac

import pytest

from src.pay_per_crawl.audit_identity import audit_token


def test_audit_token_uses_configured_hmac_key(monkeypatch):
    audit_key = b"test-audit-key-with-32-bytes-minimum"
    monkeypatch.setenv("CRAWLER_AUDIT_HMAC_KEY", audit_key.decode("ascii"))

    expected = hmac.new(audit_key, b"crawler-token", hashlib.sha256).hexdigest()[:32]

    assert audit_token("crawler-token") == expected


def test_audit_token_does_not_expose_token(monkeypatch):
    monkeypatch.delenv("CRAWLER_AUDIT_HMAC_KEY", raising=False)

    identifier = audit_token("crawler-token")

    assert identifier != "crawler-token"
    assert len(identifier) == 32


def test_audit_token_rejects_short_configured_key(monkeypatch):
    monkeypatch.setenv("CRAWLER_AUDIT_HMAC_KEY", "too-short")

    with pytest.raises(ValueError, match="at least 32 bytes"):
        audit_token("crawler-token")
