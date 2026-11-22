"""Credentials and identity headers must not spread beyond what the engine needs (#1904)."""

import os
import unittest
from unittest.mock import patch

from src.shared import header_policy as policy

SECRETS = {
    "Authorization": "Bearer abc",
    "Proxy-Authorization": "Basic xyz",
    "Cookie": "sid=1",
    "Set-Cookie": "a=b",
    "X-API-Key": "k-123",
    "X-Auth-Token": "t",
    "X-CSRF-Token": "c",
    "X-XSRF-TOKEN": "x",
    "X-Captcha-Token": "cap",
    "X-Signature": "sig",
    "X-Request-Signature": "sig2",
    "X-Amz-Security-Token": "aws",
    "X-Internal-Secret": "shh",
    "X-Acme-Session-Id": "s",
    "X-Forwarded-For": "10.1.2.3",
    "X-Customer-Password": "pw",
    "X-Totally-Custom": "value",
    "Host": "internal.example",
}
BROWSER = {
    "Accept": "text/html",
    "Accept-Language": "en-US",
    "Accept-Encoding": "gzip",
    "Sec-CH-UA": '"Chromium";v="120"',
    "Sec-CH-UA-Platform": '"Linux"',
    "Sec-Fetch-Site": "none",
    "DNT": "1",
}


class InternalHeaders(unittest.TestCase):
    def test_only_what_the_engine_reads_survives_and_names_are_lowercased(self):
        result = policy.internal_headers({**BROWSER, **SECRETS})
        for name in SECRETS:
            if name.lower() != "x-captcha-token":
                self.assertNotIn(name.lower(), result, name)
                self.assertNotIn(name, result, name)
        self.assertEqual(result["accept-language"], "en-US")
        self.assertEqual(result["sec-fetch-site"], "none")
        self.assertEqual(result["x-captcha-token"], "cap", "the engine verifies this itself")

    def test_values_lose_control_characters_and_are_length_limited(self):
        result = policy.internal_headers({"Accept": "a\r\nb" + "x" * 2000})
        self.assertNotIn("\r", result["accept"])
        self.assertLessEqual(len(result["accept"]), 512)

    def test_none_and_empty_are_fine(self):
        self.assertEqual(policy.internal_headers(None), {})
        self.assertEqual(policy.internal_headers({}), {})


class ExternalHeaders(unittest.TestCase):
    def test_known_secret_headers_and_the_captcha_response_never_leave(self):
        result = policy.external_headers({**BROWSER, **SECRETS})
        self.assertEqual(set(result), {k.lower() for k in BROWSER})
        for name in SECRETS:
            self.assertNotIn(name.lower(), result)

    def test_only_documented_fields_pass(self):
        result = policy.external_headers({"X-Totally-Custom": "v", "Accept": "a", "User-Agent": "ua", "Referer": "r"})
        self.assertEqual(result, {"accept": "a"})

    def test_the_default_allowlists_contain_nothing_credential_like(self):
        for name in policy.EXTERNAL_HEADER_ALLOWLIST:
            self.assertFalse(policy.is_sensitive_header(name), name)
        for name in policy.INTERNAL_HEADER_ALLOWLIST - {"x-captcha-token"}:
            self.assertFalse(policy.is_sensitive_header(name), name)

    def test_an_operator_can_replace_the_list_but_not_add_credentials(self):
        headers = {"Accept": "a", "X-Trace-Id": "t1", "Authorization": "Bearer abc", "X-API-Key": "k"}
        with patch.dict(os.environ, {"EXTERNAL_API_HEADER_ALLOWLIST": "x-trace-id, authorization, x-api-key"}):
            self.assertEqual(policy.external_headers(headers), {"x-trace-id": "t1"})
        with patch.dict(os.environ, {"EXTERNAL_API_HEADER_ALLOWLIST": ""}):
            self.assertEqual(policy.external_headers(headers), {}, "an empty list sends no headers")

    def test_a_configured_header_survives_the_way_in_so_the_override_actually_works(self):
        headers = {"X-Trace-Id": "trace-123", "Authorization": "Bearer abc", "Accept": "a"}
        with patch.dict(os.environ, {"EXTERNAL_API_HEADER_ALLOWLIST": "x-trace-id,authorization,accept"}):
            inside = policy.internal_headers(headers)
            self.assertEqual(inside, {"x-trace-id": "trace-123", "accept": "a"})
            self.assertEqual(policy.external_headers(inside), {"x-trace-id": "trace-123", "accept": "a"})
        self.assertNotIn("x-trace-id", policy.internal_headers(headers), "without the setting it is dropped")

    def test_a_long_captcha_response_is_kept_intact_inside_and_never_exported(self):
        token = "r" * 3000
        inside = policy.internal_headers({"X-Captcha-Token": token, "Accept": "a"})
        self.assertEqual(inside["x-captcha-token"], token)
        self.assertNotIn("x-captcha-token", policy.external_headers(inside))

    def test_an_absurdly_long_captcha_response_is_dropped_not_truncated(self):
        inside = policy.internal_headers({"X-Captcha-Token": "r" * 9000})
        self.assertNotIn("x-captcha-token", inside)

    def test_sensitive_name_detection(self):
        for name in SECRETS:
            if name not in ("X-Forwarded-For", "X-Totally-Custom", "Host"):
                self.assertTrue(policy.is_sensitive_header(name), name)
        for name in ("Accept", "Accept-Language", "Sec-Fetch-Mode", "User-Agent", "Content-Type"):
            self.assertFalse(policy.is_sensitive_header(name), name)


if __name__ == "__main__":
    unittest.main()
