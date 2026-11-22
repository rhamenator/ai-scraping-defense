"""Credential-bearing webhook URLs must not reach any log (#1906)."""

import asyncio
import io
import logging
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from src.shared import url_redaction
from src.shared.url_redaction import (
    UrlRedactionFilter,
    install_url_redaction,
    redact_urls,
    safe_endpoint_for_logs,
)

CANARY = "CANARY-WEBHOOK-TOKEN-9f3a"
SECRET_URL = f"https://hooks.example.com/services/T000/B000/{CANARY}?key={CANARY}"


def _capture(logger: logging.Logger) -> io.StringIO:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return stream


class RedactionHelperTests(unittest.TestCase):
    def test_safe_form_is_origin_plus_stable_fingerprint(self):
        safe = safe_endpoint_for_logs(SECRET_URL)
        self.assertTrue(safe.startswith("https://hooks.example.com (id="))
        self.assertNotIn(CANARY, safe)
        self.assertEqual(safe, safe_endpoint_for_logs(SECRET_URL))
        self.assertNotEqual(safe, safe_endpoint_for_logs(SECRET_URL + "x"))

    def test_userinfo_path_query_and_fragment_are_all_removed(self):
        for url in (
            f"https://user:{CANARY}@hooks.example.com/",
            f"https://hooks.example.com/a/{CANARY}",
            f"https://hooks.example.com/?token={CANARY}",
            f"https://hooks.example.com/#{CANARY}",
            f"HTTPS://HOOKS.example.com:8443/{CANARY}",
        ):
            self.assertNotIn(CANARY, redact_urls(f"failed for url '{url}'."), url)
            self.assertNotIn(CANARY, safe_endpoint_for_logs(url), url)

    def test_ipv6_hosts_and_brackets_inside_a_url_do_not_stop_the_match(self):
        """The credential must go even when the URL has an IPv6 authority or parentheses in its query."""
        for url in (
            f"http://[2001:db8::1]:8443/hook/{CANARY}",
            f"https://example.com/hook?x=(foo)&token={CANARY}",
            f"https://example.com/a[1]/{CANARY}",
            f"https://example.com/{{a}}/{CANARY}",
        ):
            for wrapper in ("{}", "failed for url '{}'", "(see {})", "[{}]", "{}."):
                result = redact_urls(wrapper.format(url))
                self.assertNotIn(CANARY, result, wrapper.format(url))
                self.assertIn("(id=", result)
        self.assertIn("[2001:db8::1]:8443", redact_urls(f"http://[2001:db8::1]:8443/hook/{CANARY}"))

    def test_surrounding_brackets_and_punctuation_are_kept(self):
        self.assertTrue(redact_urls(f"(see https://example.com/{CANARY})").endswith(")"))
        self.assertTrue(redact_urls(f"(see https://example.com/{CANARY})").startswith("(see "))
        self.assertTrue(redact_urls(f"[https://example.com/{CANARY}]").endswith("]"))
        self.assertTrue(redact_urls(f"see https://example.com/{CANARY}, then").endswith(", then"))
        # a bracket that belongs to the URL stays inside the match, a closing one that does not is kept outside
        balanced = redact_urls("link https://example.com/wiki/Rust_(language) done")
        self.assertTrue(balanced.endswith(" done"))

    def test_bare_origins_and_ordinary_text_are_left_alone(self):
        for text in (
            "connecting to http://redis:6379",
            "see https://example.com/ for docs",
            "no url here",
            "",
        ):
            self.assertEqual(redact_urls(text), text)

    def test_sentence_punctuation_is_kept_and_several_urls_are_handled(self):
        text = f"first {SECRET_URL}, then https://other.example.net/{CANARY}."
        result = redact_urls(text)
        self.assertNotIn(CANARY, result)
        self.assertTrue(result.endswith("."))
        self.assertIn(", then ", result)
        self.assertEqual(redact_urls(result), result)  # idempotent

    def test_ipv6_origin_and_malformed_urls_do_not_raise(self):
        self.assertIn("[::1]:8080", safe_endpoint_for_logs(f"http://[::1]:8080/{CANARY}"))
        self.assertNotIn(CANARY, redact_urls(f"bad http://[::1/{CANARY} here"))
        self.assertEqual(safe_endpoint_for_logs("not a url").split(" ")[0], "<invalid-url>")


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger("test.url_redaction.filter")
        self.logger.handlers.clear()
        self.logger.filters.clear()
        install_url_redaction(self.logger)
        install_url_redaction(self.logger)  # idempotent
        self.stream = _capture(self.logger)
        self.addCleanup(self.logger.handlers.clear)

    def test_installed_once(self):
        self.assertEqual(sum(isinstance(f, UrlRedactionFilter) for f in self.logger.filters), 1)

    def test_message_arguments_and_exception_text_are_scrubbed(self):
        self.logger.error("endpoint %s failed", SECRET_URL)
        self.logger.error(f"fstring {SECRET_URL}")
        try:
            raise httpx.HTTPStatusError(
                f"Client error '404 Not Found' for url '{SECRET_URL}'",
                request=httpx.Request("POST", SECRET_URL),
                response=httpx.Response(404, request=httpx.Request("POST", SECRET_URL)),
            )
        except httpx.HTTPStatusError:
            self.logger.exception("delivery failed")
        output = self.stream.getvalue()
        self.assertNotIn(CANARY, output)
        self.assertIn("hooks.example.com (id=", output)
        self.assertIn("Traceback", output)

    def test_a_malformed_format_string_does_not_break_logging(self):
        self.logger.error("needs two %s %s", SECRET_URL)
        output = self.stream.getvalue()
        self.assertNotIn(CANARY, output)
        self.assertIn("needs two", output)


class LogErrorTests(unittest.TestCase):
    def test_log_error_scrubs_the_message_and_the_exception_text(self):
        from src.shared import utils

        captured = io.StringIO()
        sink = logging.getLogger("test.url_redaction.log_error")
        sink.handlers.clear()
        sink.addHandler(logging.StreamHandler(captured))
        sink.setLevel(logging.DEBUG)
        error = httpx.HTTPStatusError(
            f"Server error for url '{SECRET_URL}'",
            request=httpx.Request("POST", SECRET_URL),
            response=httpx.Response(500, request=httpx.Request("POST", SECRET_URL)),
        )
        with patch.object(utils, "_error_logger", sink):
            utils.log_error(f"Failed to send alert to {SECRET_URL}", error)
        self.assertNotIn(CANARY, captured.getvalue())
        self.assertIn("hooks.example.com", captured.getvalue())


class AlertSinkTests(unittest.TestCase):
    """The real failure paths, with a canary token in the configured webhook URL."""

    def _capture_everything(self):
        from src.shared import utils

        stream = io.StringIO()
        sink = logging.getLogger("test.url_redaction.alert_sink")
        sink.handlers.clear()
        sink.addHandler(logging.StreamHandler(stream))
        sink.setLevel(logging.DEBUG)
        for name in ("src.ai_service.alerts", "src.escalation.escalation_engine"):
            logger = logging.getLogger(name)
            handler = logging.StreamHandler(stream)
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
            self.addCleanup(logger.removeHandler, handler)
        patcher = patch.object(utils, "_error_logger", sink)
        patcher.start()
        self.addCleanup(patcher.stop)
        return stream

    def test_legacy_generic_webhook_failures_do_not_log_the_url(self):
        from src.ai_service import alerts

        stream = self._capture_everything()
        event = MagicMock()
        event.details = {"ip": "203.0.113.5"}
        event.reason = "test"
        request = httpx.Request("POST", SECRET_URL)
        failures = (
            httpx.ConnectError(f"cannot connect to {SECRET_URL}", request=request),
            httpx.HTTPStatusError(
                f"Client error for url '{SECRET_URL}'",
                request=request,
                response=httpx.Response(500, request=request),
            ),
        )
        for failure in failures:
            client = MagicMock()
            client.post = AsyncMock(side_effect=failure)
            context = MagicMock()
            context.__aenter__ = AsyncMock(return_value=client)
            context.__aexit__ = AsyncMock(return_value=False)
            with patch.object(alerts, "ALERT_GENERIC_WEBHOOK_URL", SECRET_URL), patch.object(
                alerts.httpx, "AsyncClient", return_value=context
            ), patch.object(alerts, "_webhook_payload", return_value={"x": 1}):
                asyncio.run(alerts._send_generic_webhook_alert_legacy(event))
        output = stream.getvalue()
        self.assertNotIn(CANARY, output)
        self.assertIn("hooks.example.com", output)

    def test_escalation_webhook_failures_do_not_log_the_url(self):
        from src.escalation import escalation_engine as engine

        stream = self._capture_everything()
        request = httpx.Request("POST", SECRET_URL)
        for failure in (
            httpx.ConnectError(f"cannot connect to {SECRET_URL}", request=request),
            httpx.HTTPStatusError(
                f"Server error for url '{SECRET_URL}'",
                request=request,
                response=httpx.Response(500, request=request),
            ),
        ):
            client = MagicMock()
            client.post = AsyncMock(side_effect=failure)
            context = MagicMock()
            context.__aenter__ = AsyncMock(return_value=client)
            context.__aexit__ = AsyncMock(return_value=False)
            with patch.object(engine, "WEBHOOK_URL", SECRET_URL), patch.object(
                engine, "APPROVED_WEBHOOK_DOMAINS", []
            ), patch.object(engine.httpx, "AsyncClient", return_value=context):
                asyncio.run(engine.forward_to_webhook({"ip": "203.0.113.5"}, "test"))
        output = stream.getvalue()
        self.assertNotIn(CANARY, output)
        self.assertIn("hooks.example.com", output)

    def test_the_module_loggers_carry_the_filter(self):
        from src.ai_service import alerts
        from src.escalation import escalation_engine
        from src.shared import http_alert

        for module in (alerts, escalation_engine, http_alert):
            self.assertTrue(
                any(isinstance(f, UrlRedactionFilter) for f in module.logger.filters),
                module.__name__,
            )

    def test_the_startup_line_shows_the_origin_and_fingerprint_only(self):
        from src.escalation import escalation_engine as engine

        line = f"Webhook URL configured: {'Yes (' + engine.safe_endpoint_for_logs(SECRET_URL) + ')'}"
        self.assertNotIn(CANARY, line)
        source = open(engine.__file__, encoding="utf-8").read()
        self.assertNotIn("str(WEBHOOK_URL) +", source)

    def test_http_alert_keeps_its_private_alias(self):
        from src.shared import http_alert

        self.assertIs(http_alert._safe_endpoint_for_logs, url_redaction.safe_endpoint_for_logs)
