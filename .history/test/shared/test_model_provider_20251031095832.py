import unittest
from unittest.mock import patch
import os

from src.shared import model_provider


class DummyAdapter:
    def __init__(self, uri):
        self.uri = uri

class FlakyAdapter:
    attempts = 0

    def __init__(self, uri, config=None):
        FlakyAdapter.attempts += 1
        if FlakyAdapter.attempts < 3:
            raise ValueError("fail")
        self.uri = uri


class AlwaysFailAdapter:
    def __init__(self, uri, config=None):
        raise ValueError("fail")


class TestGetModelAdapter(unittest.TestCase):
    def test_returns_correct_adapter_instance(self):
        with patch.dict(
            os.environ, {"MODEL_URI": "sklearn:///model.joblib"}
        ), patch.dict(
            model_provider.ADAPTER_MAP, {"sklearn": DummyAdapter}, clear=True
        ):
            adapter = model_provider.get_model_adapter()
            self.assertIsInstance(adapter, DummyAdapter)
            self.assertEqual(adapter.uri, "/model.joblib")

    def test_invalid_scheme_returns_none(self):
        with patch.dict(os.environ, {"MODEL_URI": "invalid:///model"}), patch.dict(
            model_provider.ADAPTER_MAP, {"sklearn": DummyAdapter}, clear=True
        ), patch("logging.error") as mock_log:
            adapter = model_provider.get_model_adapter()
            mock_log.assert_called()
            self.assertIsNone(adapter)

    def test_retry_then_success(self):
        FlakyAdapter.attempts = 0
        with patch.dict(
            os.environ,
            {"MODEL_URI": "sklearn:///model.joblib"},
        ), patch.dict(
            model_provider.ADAPTER_MAP, {"sklearn": FlakyAdapter}, clear=True
        ), patch("time.sleep") as mock_sleep:
            adapter = model_provider.get_model_adapter(retries=3, delay=0)
            self.assertIsInstance(adapter, FlakyAdapter)
            self.assertEqual(FlakyAdapter.attempts, 3)
            self.assertEqual(mock_sleep.call_count, 2)

    def test_retries_exhausted_returns_none(self):
        with patch.dict(
            os.environ,
            {"MODEL_URI": "sklearn:///model.joblib"},
        ), patch.dict(
            model_provider.ADAPTER_MAP, {"sklearn": AlwaysFailAdapter}, clear=True
        ), patch("time.sleep") as mock_sleep:
            adapter = model_provider.get_model_adapter(retries=2, delay=0)
            self.assertIsNone(adapter)
            self.assertEqual(mock_sleep.call_count, 1)

    def test_mcp_scheme_preserves_full_uri(self):
        class CaptureAdapter:
            def __init__(self, uri, config=None):
                self.uri = uri
                self.config = config

        with patch.dict(
            os.environ,
            {"MODEL_URI": "mcp://insights/deep-scan"},
        ), patch.dict(
            model_provider.ADAPTER_MAP, {"mcp": CaptureAdapter}, clear=True
        ):
            adapter = model_provider.get_model_adapter()
            self.assertIsInstance(adapter, CaptureAdapter)
            self.assertEqual(adapter.uri, "mcp://insights/deep-scan")


if __name__ == "__main__":
    unittest.main()
