"""What the escalation engine sends outward must carry only allowlisted headers (#1904)."""

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.escalation import escalation_engine as engine
from src.escalation.escalation_engine import RequestMetadata
from src.tarpit.tarpit_api import EscalationMetadata

HEADERS = {
    "accept-language": "en-US",
    "accept": "text/html",
    "authorization": "Bearer abc",
    "cookie": "sid=1",
    "x-api-key": "k-123",
    "x-custom-secret": "shh-very-secret",
    "x-csrf-token": "csrf-1",
    "proxy-authorization": "Basic zzz",
    "x-signature": "sig-9",
    "x-captcha-token": "captcha-response",
    "x-forwarded-for": "10.9.8.7",
}
SECRET_VALUES = ("Bearer abc", "sid=1", "k-123", "shh-very-secret", "csrf-1", "Basic zzz", "sig-9", "captcha-response", "10.9.8.7")


def metadata() -> RequestMetadata:
    return RequestMetadata(timestamp="2026-11-22T00:00:00Z", ip="203.0.113.9", user_agent="ua", path="/p", method="GET",
                           headers=HEADERS, source="test")


class OutboundMetadata(unittest.IsolatedAsyncioTestCase):
    def assertNoSecrets(self, value):
        text = repr(value)
        for secret in SECRET_VALUES:
            self.assertNotIn(secret, text)

    def test_the_tarpit_forwards_only_what_the_engine_needs(self):
        forwarded = EscalationMetadata(timestamp="t", ip="203.0.113.9", method="GET", path="/", headers=HEADERS).model_dump()
        self.assertEqual(forwarded["headers"]["accept-language"], "en-US")
        for name in ("authorization", "cookie", "x-api-key", "x-custom-secret", "x-csrf-token", "proxy-authorization", "x-signature", "x-forwarded-for"):
            self.assertNotIn(name, forwarded["headers"])

    def test_the_engine_drops_secret_headers_even_from_other_callers(self):
        kept = metadata().headers
        for name in ("authorization", "cookie", "x-api-key", "x-custom-secret", "x-csrf-token", "x-forwarded-for"):
            self.assertNotIn(name, kept)
        self.assertEqual(kept["x-captcha-token"], "captcha-response")

    async def test_the_external_classifier_receives_only_documented_headers(self):
        adapter = MagicMock()
        adapter.predict.return_value = {"is_bot": True}
        with patch.object(engine, "external_api_adapter", adapter):
            await engine.classify_with_external_api(metadata())
        sent = adapter.predict.call_args.args[0]
        self.assertEqual(sent["headers"], {"accept-language": "en-US", "accept": "text/html"})
        self.assertNoSecrets(sent)

    async def test_the_external_classifier_gets_nothing_extra_even_if_the_internal_copy_had_it(self):
        meta = metadata()
        meta.headers = dict(HEADERS)  # bypass validation: a stored copy that somehow kept everything
        adapter = MagicMock()
        adapter.predict.return_value = {"is_bot": False}
        with patch.object(engine, "external_api_adapter", adapter):
            await engine.classify_with_external_api(meta)
        self.assertNoSecrets(adapter.predict.call_args.args[0])

    async def test_the_local_model_and_the_exported_record_are_filtered_too(self):
        adapter = MagicMock()
        adapter.predict.return_value = {"classification": "HUMAN"}
        with patch.object(engine, "local_llm_adapter", adapter):
            await engine.classify_with_local_llm_api(metadata())
        self.assertNoSecrets(adapter.predict.call_args.args[0])
        self.assertNoSecrets(engine.export_metadata(metadata(), mode="json"))

    async def test_the_blocklist_record_and_the_webhook_body_carry_no_secrets(self):
        seen = {}
        webhook = AsyncMock()
        with patch.object(engine, "add_ip_to_blocklist", side_effect=lambda ip, reason, payload: seen.update(payload=payload) or True), \
                patch.object(engine, "forward_to_webhook", webhook), patch.object(engine, "publish_operational_event"), \
                patch.object(engine, "_determine_containment_level", return_value="block"):
            await engine._apply_containment_action(metadata(), score=0.99, source="test")
        self.assertNoSecrets(seen["payload"])
        self.assertNoSecrets(webhook.await_args.args[0])

    async def test_the_engine_still_verifies_a_captcha_response_it_received(self):
        meta = metadata()
        with patch.object(engine, "CAPTCHA_SECRET", "s"), patch("src.escalation.escalation_engine.httpx.AsyncClient") as client:
            client.return_value.__aenter__.return_value.post = AsyncMock(return_value=MagicMock(json=lambda: {"success": True}, raise_for_status=lambda: None))
            result = await engine.trigger_captcha_challenge(meta)
        self.assertTrue(result, "the CAPTCHA response must still reach the verifier inside the engine")

    def test_fingerprinting_still_sees_its_inputs(self):
        a = metadata()
        b = metadata()
        b.headers = {**b.headers, "accept-language": "fr-FR"}
        self.assertNotEqual(engine.compute_browser_fingerprint(a), engine.compute_browser_fingerprint(b))


if __name__ == "__main__":
    unittest.main()
