import os
import unittest

os.environ.setdefault("SYSTEM_SEED", "test-seed")
from src.tarpit import tarpit_api


class TestSanitizeHeaders(unittest.TestCase):
    def test_sanitize_headers_removes_sensitive_and_normalizes(self):
        headers = {
            "User-Agent": "Test",
            "Authorization": "secret",
            "Cookie": "a=b",
            "X-Custom": "value",
            "multiline": "line1\nline2\rline3",
        }
        result = tarpit_api.sanitize_headers(headers)
        self.assertIn("User-Agent", result)
        self.assertIn("X-Custom", result)
        self.assertEqual(result["multiline"], "line1line2line3")
        self.assertNotIn("Authorization", result)
        self.assertNotIn("Cookie", result)


if __name__ == "__main__":
    unittest.main()
