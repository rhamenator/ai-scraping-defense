import unittest
from unittest.mock import patch
import os

from src.shared import model_provider


class DummyAdapter:
    def __init__(self, uri):
        self.uri = uri


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


if __name__ == "__main__":
    unittest.main()
