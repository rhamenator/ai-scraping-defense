import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.shared.mcp_client import MCPClient, MCPServerConfig, load_server_config


class FakeTransport:
    async def __aenter__(self):
        return "read-stream", "write-stream"

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeSession:
    last_instance = None

    def __init__(self, read_stream, write_stream):
        self.read_stream = read_stream
        self.write_stream = write_stream
        self.initialized = False
        FakeSession.last_instance = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def initialize(self):
        self.initialized = True

    async def call_tool(self, name, arguments):
        return SimpleNamespace(structuredContent={"tool": name, "arguments": arguments})


class TestMCPClient(unittest.TestCase):
    def test_http_transport_is_accepted(self):
        config = load_server_config(
            "custom",
            overrides={"transport": "http", "url": "https://example.test/mcp"},
        )
        self.assertEqual(config.transport, "http")
        self.assertEqual(config.endpoint, "https://example.test/mcp")

    def test_session_uses_transport_streams_and_initializes(self):
        config = MCPServerConfig(
            label="test", transport="ws", endpoint="ws://localhost/mcp"
        )
        client = MCPClient(config)

        with (
            patch("src.shared.mcp_client.ClientSession", FakeSession),
            patch.object(client, "_create_transport", return_value=FakeTransport()),
        ):
            result = asyncio.run(client._call_tool("classify", {"path": "/"}, 1.0))

        self.assertTrue(FakeSession.last_instance.initialized)
        self.assertEqual(FakeSession.last_instance.read_stream, "read-stream")
        self.assertEqual(result, {"tool": "classify", "arguments": {"path": "/"}})


if __name__ == "__main__":
    unittest.main()
