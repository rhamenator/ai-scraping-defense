import json
import unittest
from unittest.mock import patch

from scripts import populate_problem_metadata


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        payload = {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
        return json.dumps(payload).encode("utf-8")


class TestPopulateProblemMetadata(unittest.TestCase):
    def test_call_gemini_uses_expected_https_endpoint_and_timeout(self):
        with patch.object(populate_problem_metadata, "API_KEY", "test-key"):
            with patch(
                "scripts.populate_problem_metadata.urllib.request.urlopen",
                return_value=FakeResponse(),
            ) as mock_urlopen:
                result = populate_problem_metadata.call_gemini("hello")

        self.assertEqual(result, "ok")
        request = mock_urlopen.call_args.args[0]
        timeout = mock_urlopen.call_args.kwargs["timeout"]

        self.assertTrue(
            request.full_url.startswith(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash"
            )
        )
        self.assertEqual(timeout, populate_problem_metadata.GEMINI_API_TIMEOUT_SECONDS)


if __name__ == "__main__":
    unittest.main()
