"""Redirects and DNS rebinding must not get past SSRF protection (#1905)."""

import socket
import unittest
from unittest.mock import patch

import httpx

from src.shared.http_client import AsyncHttpClient
from src.shared.ssrf_protection import SSRFProtectionError

PUBLIC = "93.184.216.34"
OTHER_PUBLIC = "1.1.1.1"


def _answer(address: str):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))]


class Recorder:
    """A mock transport that records every request it receives and answers from a script."""

    def __init__(self, script):
        self.requests: list[httpx.Request] = []
        self.script = script  # callable(request) -> httpx.Response

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.script(request)


def redirect(status: int, location: str):
    return lambda request: httpx.Response(status, headers={"location": location}, request=request)


class RedirectTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dns = {"example.test": [PUBLIC], "other.test": [OTHER_PUBLIC], "internal.test": ["10.0.0.5"]}
        def lookup(host, port, **kw):
            if host in self.dns:
                return _answer(self.dns[host][0])
            try:
                socket.inet_pton(socket.AF_INET6 if ":" in host else socket.AF_INET, host)
                return _answer(host)  # an IP literal resolves to itself
            except OSError:
                raise OSError("no such host") from None

        patcher = patch("src.shared.ssrf_protection.socket.getaddrinfo", side_effect=lookup)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def client_for(self, recorder: Recorder, **kwargs) -> AsyncHttpClient:
        client = AsyncHttpClient(**kwargs)
        await client.__aenter__()
        self.addAsyncCleanup(client.__aexit__, None, None, None)
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(recorder), follow_redirects=False)
        self.addAsyncCleanup(client._client.aclose)
        return client

    # ---- defaults ------------------------------------------------------------------------------------------

    async def test_redirects_are_not_followed_by_default(self):
        recorder = Recorder(redirect(302, "http://169.254.169.254/latest/meta-data"))
        client = await self.client_for(recorder)

        response = await client.async_get("https://example.test/start")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(recorder.requests), 1, "the redirect target must never be contacted")

    def test_the_default_and_the_underlying_client_never_follow_redirects(self):
        self.assertFalse(AsyncHttpClient().follow_redirects)

    # ---- every hop is validated ----------------------------------------------------------------------------

    async def test_a_redirect_to_an_internal_address_is_refused_before_it_is_requested(self):
        targets = [
            "http://169.254.169.254/latest/meta-data/",
            "http://127.0.0.1:8080/admin",
            "http://localhost/admin",
            "http://10.0.0.5/",
            "http://192.168.1.1/",
            "http://172.16.0.9/",
            "http://[::1]/",
            "http://[fe80::1]/",
            "http://internal.test/",          # a name that resolves to a private address
            "http://0.0.0.0/",
        ]
        for target in targets:
            with self.subTest(target=target):
                recorder = Recorder(redirect(302, target))
                client = await self.client_for(recorder, follow_redirects=True)
                with self.assertRaises(SSRFProtectionError):
                    await client.async_get("https://example.test/start")
                self.assertEqual(len(recorder.requests), 1, f"{target} was contacted")

    async def test_a_redirect_to_another_public_host_is_followed(self):
        def script(request):
            if request.url.host == "example.test":
                return redirect(302, "https://other.test/final")(request)
            return httpx.Response(200, text="done", request=request)

        recorder = Recorder(script)
        client = await self.client_for(recorder, follow_redirects=True)

        response = await client.async_get("https://example.test/start")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([r.url.host for r in recorder.requests], ["example.test", "other.test"])
        self.assertEqual([r.headers["host"] for r in recorder.requests], ["example.test", "other.test"])

    async def test_a_redirect_that_downgrades_https_to_http_is_refused(self):
        recorder = Recorder(redirect(302, "http://other.test/plain"))
        client = await self.client_for(recorder, follow_redirects=True)
        with self.assertRaises(SSRFProtectionError) as caught:
            await client.async_get("https://example.test/start")
        self.assertIn("HTTPS to HTTP", str(caught.exception))
        self.assertEqual(len(recorder.requests), 1)

    async def test_the_redirect_limit_is_enforced(self):
        recorder = Recorder(redirect(302, "https://example.test/loop"))
        client = await self.client_for(recorder, follow_redirects=True, max_redirects=3)
        with self.assertRaises(httpx.TooManyRedirects):
            await client.async_get("https://example.test/start")
        self.assertEqual(len(recorder.requests), 4)  # the first request plus three followed hops

    async def test_a_redirect_outside_the_domain_allowlist_is_refused(self):
        recorder = Recorder(redirect(302, "https://other.test/x"))
        client = await self.client_for(recorder, follow_redirects=True, allowed_domains=["example.test"])
        with self.assertRaises(SSRFProtectionError):
            await client.async_get("https://example.test/start")
        self.assertEqual(len(recorder.requests), 1)

    async def test_a_redirect_to_a_relative_location_stays_on_the_same_host(self):
        def script(request):
            if request.url.path == "/start":
                return redirect(301, "/next")(request)
            return httpx.Response(200, text="ok", request=request)

        recorder = Recorder(script)
        client = await self.client_for(recorder, follow_redirects=True)
        response = await client.async_get("https://example.test/start")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([r.url.path for r in recorder.requests], ["/start", "/next"])

    # ---- what travels with a redirect ----------------------------------------------------------------------

    async def test_credentials_are_dropped_when_a_redirect_leaves_the_origin_but_kept_within_it(self):
        def script(request):
            if request.url.path == "/start":
                return redirect(302, "https://other.test/elsewhere")(request)
            return httpx.Response(200, request=request)

        recorder = Recorder(script)
        client = await self.client_for(recorder, follow_redirects=True)
        await client.async_get(
            "https://example.test/start",
            headers={"Authorization": "Bearer abc", "X-API-Key": "k", "Cookie": "s=1", "Accept": "text/plain"},
        )
        first, second = recorder.requests
        self.assertEqual(first.headers["authorization"], "Bearer abc")
        for credential in ("authorization", "x-api-key", "cookie"):
            self.assertNotIn(credential, second.headers)
        self.assertEqual(second.headers["accept"], "text/plain")

        recorder.requests.clear()
        recorder.script = lambda r: redirect(302, "https://example.test/same")(r) if r.url.path == "/start" else httpx.Response(200, request=r)
        await client.async_get("https://example.test/start", headers={"Authorization": "Bearer abc"})
        self.assertEqual(recorder.requests[1].headers["authorization"], "Bearer abc", "same origin keeps its credentials")

    async def test_a_303_turns_a_post_into_a_get_without_a_body_and_a_307_keeps_both(self):
        for status, method, has_body in ((303, "GET", False), (307, "POST", True), (308, "POST", True)):
            with self.subTest(status=status):
                def script(request, status=status):
                    if request.url.path == "/start":
                        return redirect(status, "/after")(request)
                    return httpx.Response(200, request=request)

                recorder = Recorder(script)
                client = await self.client_for(recorder, follow_redirects=True)
                await client.async_post_json("https://example.test/start", {"a": 1})
                final = recorder.requests[-1]
                self.assertEqual(final.method, method)
                self.assertEqual(bool(final.content), has_body)
                self.assertEqual("content-type" in final.headers, has_body)

    # ---- DNS rebinding -------------------------------------------------------------------------------------

    async def test_a_name_with_any_private_address_among_several_is_refused(self):
        def mixed(host, port, **kw):
            return _answer(PUBLIC) + _answer("10.0.0.5")

        with patch("src.shared.ssrf_protection.socket.getaddrinfo", side_effect=mixed):
            recorder = Recorder(lambda r: httpx.Response(200, request=r))
            client = await self.client_for(recorder)
            with self.assertRaises(SSRFProtectionError):
                await client.async_get("https://example.test/data")
        self.assertEqual(recorder.requests, [])


if __name__ == "__main__":
    unittest.main()
