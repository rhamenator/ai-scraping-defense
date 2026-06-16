import unittest

from src.shared.mcp_client import _normalise_tool_result


class _ModelDumpFailure:
    def model_dump(self):
        raise RuntimeError("model dump failed")

    def __repr__(self):
        return "<model-dump-failure>"


class _DictFailure:
    def dict(self):
        raise RuntimeError("dict failed")

    def __repr__(self):
        return "<dict-failure>"


class TestMCPClient(unittest.TestCase):
    def test_normalise_tool_result_logs_model_dump_failures(self):
        with self.assertLogs("src.shared.mcp_client", level="WARNING") as logs:
            result = _normalise_tool_result(_ModelDumpFailure())
        log_output = "\n".join(logs.output)
        self.assertEqual(result, {"raw": "<model-dump-failure>"})
        self.assertIn("Failed to normalize MCP result via model_dump()", log_output)
        self.assertIn("model dump failed", log_output)

    def test_normalise_tool_result_logs_dict_failures(self):
        with self.assertLogs("src.shared.mcp_client", level="WARNING") as logs:
            result = _normalise_tool_result(_DictFailure())
        log_output = "\n".join(logs.output)
        self.assertEqual(result, {"raw": "<dict-failure>"})
        self.assertIn("Failed to normalize MCP result via dict()", log_output)
        self.assertIn("dict failed", log_output)


if __name__ == "__main__":
    unittest.main()
