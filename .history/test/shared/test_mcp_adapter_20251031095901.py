import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.shared.model_adapters import MCPAdapter
from src.shared.mcp_client import MCPClientError


class TestMCPAdapter(unittest.TestCase):
    @patch("src.shared.model_adapters.MCPClient")
    @patch("src.shared.model_adapters.load_server_config")
    @patch("src.shared.model_adapters.parse_mcp_uri")
    def test_predict_success(self, mock_parse, mock_load_config, mock_client_cls):
        mock_parse.return_value = ("demo", "summarize", {})
        server_config = SimpleNamespace(
            label="demo",
            transport="ws",
            endpoint="ws://demo.example/mcp",
            headers={},
            args=[],
            env={},
            executable=None,
            session_name="client",
            timeout=12.0,
        )
        mock_load_config.return_value = server_config
        client_instance: MagicMock = mock_client_cls.return_value
        client_instance.call_tool.return_value = {"content": [{"type": "text", "text": "ok"}]}

        adapter = MCPAdapter("mcp://demo/summarize", config={"argument_key": "payload"})
        payload = {"prompt": "hello"}
        result = adapter.predict(payload, temperature=0.2)

        expected_arguments = {"payload": payload, "options": {"temperature": 0.2}}
        client_instance.call_tool.assert_called_once_with("summarize", expected_arguments, timeout=None)
        self.assertEqual(result, {"content": [{"type": "text", "text": "ok"}]})

    @patch("src.shared.model_adapters.MCPClient")
    @patch("src.shared.model_adapters.load_server_config")
    @patch("src.shared.model_adapters.parse_mcp_uri")
    def test_predict_returns_error_when_call_fails(
        self, mock_parse, mock_load_config, mock_client_cls
    ):
        mock_parse.return_value = ("alerts", "classify", {})
        server_config = SimpleNamespace(
            label="alerts",
            transport="ws",
            endpoint="ws://alerts/mcp",
            headers={},
            args=[],
            env={},
            executable=None,
            session_name="client",
            timeout=5.0,
        )
        mock_load_config.return_value = server_config
        client_instance: MagicMock = mock_client_cls.return_value
        client_instance.call_tool.side_effect = MCPClientError("boom")

        adapter = MCPAdapter("mcp://alerts/classify")
        response = adapter.predict({"prompt": "data"})
        self.assertEqual(response, {"error": "boom"})


if __name__ == "__main__":
    unittest.main()
