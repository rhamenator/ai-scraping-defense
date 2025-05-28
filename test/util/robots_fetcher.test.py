# test\util\robots_fetcher.test.py
import unittest
from unittest.mock import patch
from util import robots_fetcher

class TestRobotsFetcher(unittest.TestCase):

    @patch("util.robots_fetcher.requests.get")
    def test_fetch_robots_txt_success(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "User-agent: *\nDisallow: /private"
        result = robots_fetcher.fetch_robots_txt("http://example.com")
        self.assertIn("Disallow", result)

    @patch("util.robots_fetcher.requests.get")
    def test_fetch_robots_txt_failure(self, mock_get):
        mock_get.return_value.status_code = 404
        with self.assertRaises(ValueError):
            robots_fetcher.fetch_robots_txt("http://nonexistent.com")

    def test_parse_disallow_directives(self):
        robots_txt = """
        User-agent: *
        Disallow: /admin
        Disallow: /private
        """
        directives = robots_fetcher.parse_disallow(robots_txt)
        self.assertIn("/admin", directives)
        self.assertIn("/private", directives)
        self.assertNotIn("/public", directives)

if __name__ == '__main__':
    unittest.main()
