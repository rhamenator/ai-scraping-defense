"""The connection itself is checked: hostname-keyed pooling and cookies, connect-time validation, address fallback (#1905)."""

import asyncio
import socket
import unittest
from unittest.mock import patch

import httpcore

from src.shared.http_client import AsyncHttpClient
from src.shared.ssrf_protection import SSRFProtectionError
from src.shared.validated_transport import ValidatedBackend, ValidatedTransport


class LocalServer:
    """A tiny keep-alive HTTP/1.1 server on 127.0.0.1 that records connections and requests."""

    def __init__(self, set_cookie_for_host=None):
        self.connections = 0
        self.requests: list[dict] = []
        self.set_cookie_for_host = set_cookie_for_host

    async def start(self):
        self.server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()

    @staticmethod
    def _parse(head: bytes):
        lines = head.decode().split("\r\n")
        pairs = (line.split(": ", 1) for line in lines[1:] if ": " in line)
        return lines[0], {k.lower(): v for k, v in pairs}

    def _response(self, headers) -> bytes:
        cookie = ""
        if self.set_cookie_for_host and headers.get("host", "").startswith(self.set_cookie_for_host):
            cookie = "Set-Cookie: session=SECRET; Path=/\r\n"
        return f"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n{cookie}\r\nok".encode()

    async def _serve(self, reader, writer):
        self.connections += 1
        try:
            while True:
                line, headers = self._parse(await reader.readuntil(b"\r\n\r\n"))
                self.requests.append({"line": line, "headers": headers, "connection": self.connections})
                writer.write(self._response(headers))
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()


def lookup_to(address_for):
    def fake(host, port, *args, **kwargs):
        address = address_for(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, port))]

    return fake


class ValidatedTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = LocalServer(set_cookie_for_host="example.test")
        await self.server.start()
        self.addAsyncCleanup(self.server.stop)

    def reach_loopback(self):
        """Let the checks accept 127.0.0.1 (the test server) and resolve every test name to it."""
        for target in (
            patch("src.shared.ssrf_protection.socket.getaddrinfo", side_effect=lookup_to(lambda h: "127.0.0.1")),
            patch("src.shared.ssrf_protection.is_private_ip", return_value=False),
        ):
            target.start()
            self.addCleanup(target.stop)

    async def test_the_connection_uses_the_resolved_address_and_the_request_keeps_its_hostname(self):
        self.reach_loopback()
        async with AsyncHttpClient() as client:
            response = await client.async_get(f"http://example.test:{self.server.port}/a")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.server.requests[0]["headers"]["host"], f"example.test:{self.server.port}")

    async def test_two_hostnames_on_one_address_never_share_a_connection_but_one_hostname_does(self):
        self.reach_loopback()
        async with AsyncHttpClient() as client:
            await client.async_get(f"http://example.test:{self.server.port}/1")
            await client.async_get(f"http://example.test:{self.server.port}/2")
            await client.async_get(f"http://other.test:{self.server.port}/3")
        self.assertEqual(self.server.connections, 2)
        by_connection = {}
        for request in self.server.requests:
            by_connection.setdefault(request["connection"], []).append(request["headers"]["host"].split(":")[0])
        self.assertEqual(sorted(by_connection.values()), [["example.test", "example.test"], ["other.test"]])

    async def test_a_cookie_set_by_one_hostname_is_not_sent_to_another_on_the_same_address(self):
        self.reach_loopback()
        async with AsyncHttpClient() as client:
            await client.async_get(f"http://example.test:{self.server.port}/set")
            await client.async_get(f"http://other.test:{self.server.port}/elsewhere")
            await client.async_get(f"http://example.test:{self.server.port}/again")
        _, other, again = self.server.requests
        self.assertNotIn("cookie", other["headers"])
        self.assertEqual(again["headers"].get("cookie"), "session=SECRET")

    async def test_a_private_answer_at_connect_time_is_refused_even_after_a_public_one_passed_the_early_check(self):
        calls = []

        def rebinding(host, port, *args, **kwargs):
            calls.append(host)
            address = "93.184.216.34" if len(calls) == 1 else "127.0.0.1"
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, port))]

        with patch("src.shared.ssrf_protection.socket.getaddrinfo", side_effect=rebinding):
            async with AsyncHttpClient() as client:
                with self.assertRaises(SSRFProtectionError):
                    await client.async_get(f"http://example.test:{self.server.port}/x")
        self.assertEqual(self.server.connections, 0, "nothing reached the internal address")

    async def test_an_unreachable_first_address_falls_back_to_the_next_validated_one(self):
        attempts = []
        real = httpcore.AnyIOBackend.connect_tcp

        async def connect(self, host, port, *args, **kwargs):
            attempts.append(host)
            if host == "192.0.2.1":  # first validated address is unreachable
                raise httpcore.ConnectError("unreachable")
            return await real(self, host, port, *args, **kwargs)

        with patch("src.shared.validated_transport.resolve_public_addresses", return_value=["192.0.2.1", "127.0.0.1"]), \
                patch.object(httpcore.AnyIOBackend, "connect_tcp", connect):
            stream = await ValidatedBackend().connect_tcp("example.test", self.server.port)
            await stream.aclose()
        self.assertEqual(attempts, ["192.0.2.1", "127.0.0.1"])

    async def test_when_every_validated_address_fails_the_last_error_is_raised(self):
        async def connect(self, host, port, *args, **kwargs):
            raise httpcore.ConnectError(f"no route to {host}")

        with patch("src.shared.validated_transport.resolve_public_addresses", return_value=["192.0.2.1", "192.0.2.2"]), \
                patch.object(httpcore.AnyIOBackend, "connect_tcp", connect):
            with self.assertRaises(httpcore.ConnectError) as caught:
                await ValidatedBackend().connect_tcp("example.test", 80)
        self.assertIn("192.0.2.2", str(caught.exception))

    async def test_the_transport_is_used_only_while_private_address_blocking_is_on(self):
        async with AsyncHttpClient() as on, AsyncHttpClient(block_private_ips=False) as off:
            self.assertIsInstance(on._client._transport, ValidatedTransport)
            self.assertNotIsInstance(off._client._transport, ValidatedTransport)


if __name__ == "__main__":
    unittest.main()
