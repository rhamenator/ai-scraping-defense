from src.shared.tls_attestation import (
    create_tls_fingerprint_attestation,
    tls_risk_signals,
    verify_tls_fingerprint_attestation,
)

KEY = "0123456789abcdef0123456789abcdef"
JA3 = "72a589da586844d7f0818ce684948eea"
JA4 = "t13d1516h2_8daaf6152771_e5627efa2ab1"


def test_attestation_is_bound_to_request_context_and_freshness():
    token = create_tls_fingerprint_attestation(
        client_ip="198.51.100.7",
        method="get",
        path="/products",
        ja3=JA3.upper(),
        ja4=JA4.upper(),
        source="Envoy",
        key=KEY,
        issued_at=1_700_000_000,
    )
    assert token == (
        "v1:1700000000:"
        "192976122c9fbaa4cb8c2554be66f2439e020a7d470ac838f2a622b0c5829a49"
    )

    assert verify_tls_fingerprint_attestation(
        token,
        client_ip="198.51.100.7",
        method="GET",
        path="/products",
        ja3=JA3,
        ja4=JA4,
        source="envoy",
        key=KEY,
        now=1_700_000_030,
        max_age_seconds=60,
    )
    assert not verify_tls_fingerprint_attestation(
        token,
        client_ip="198.51.100.7",
        method="GET",
        path="/admin",
        ja3=JA3,
        ja4=JA4,
        source="envoy",
        key=KEY,
        now=1_700_000_030,
        max_age_seconds=60,
    )


def test_get_root_attestation_cannot_be_replayed_on_post_admin():
    token = create_tls_fingerprint_attestation(
        client_ip="198.51.100.7",
        method="GET",
        path="/",
        ja3=JA3,
        ja4=JA4,
        source="envoy",
        key=KEY,
        issued_at=1_700_000_000,
    )

    assert not verify_tls_fingerprint_attestation(
        token,
        client_ip="198.51.100.7",
        method="POST",
        path="/admin",
        ja3=JA3,
        ja4=JA4,
        source="envoy",
        key=KEY,
        now=1_700_000_030,
        max_age_seconds=60,
    )


def test_previous_key_is_accepted_only_during_rotation():
    previous_key = "abcdef0123456789abcdef0123456789"
    token = create_tls_fingerprint_attestation(
        client_ip="198.51.100.7",
        method="GET",
        path="/products",
        ja3=JA3,
        ja4=JA4,
        source="envoy",
        key=previous_key,
        issued_at=1_700_000_000,
    )

    assert verify_tls_fingerprint_attestation(
        token,
        client_ip="198.51.100.7",
        method="GET",
        path="/products",
        ja3=JA3,
        ja4=JA4,
        source="envoy",
        key=KEY,
        previous_key=previous_key,
        now=1_700_000_030,
        max_age_seconds=60,
    )
    assert not verify_tls_fingerprint_attestation(
        token,
        client_ip="198.51.100.7",
        method="GET",
        path="/products",
        ja3=JA3,
        ja4=JA4,
        source="envoy",
        key=KEY,
        previous_key=None,
        now=1_700_000_030,
        max_age_seconds=60,
    )
    assert not verify_tls_fingerprint_attestation(
        token,
        client_ip="198.51.100.7",
        method="GET",
        path="/products",
        ja3=JA3,
        ja4=JA4,
        source="envoy",
        key=KEY,
        now=1_700_000_061,
        max_age_seconds=60,
    )


def test_attestation_requires_a_strong_configured_key():
    assert (
        create_tls_fingerprint_attestation(
            client_ip="198.51.100.7",
            method="GET",
            path="/",
            ja3=JA3,
            ja4=None,
            source="envoy",
            key="too-short",
        )
        is None
    )


def test_only_verified_fingerprints_produce_risk_signals(monkeypatch):
    monkeypatch.setenv("TLS_KNOWN_BAD_JA3", JA3)
    monkeypatch.setenv("TLS_KNOWN_BAD_JA4", "")
    browser = "Mozilla/5.0 Chrome/140.0.0.0 Safari/537.36"

    assert tls_risk_signals(ja3=JA3, ja4=JA4, user_agent=browser, verified=False) == (
        False,
        False,
    )
    assert tls_risk_signals(ja3=JA3, ja4=JA4, user_agent=browser, verified=True) == (
        True,
        False,
    )
    assert tls_risk_signals(
        ja3=None,
        ja4="z99d1516h2_8daaf6152771_e5627efa2ab1",
        user_agent=browser,
        verified=True,
    ) == (False, True)
