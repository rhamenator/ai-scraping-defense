import subprocess  # nosec B404
import unittest
from unittest.mock import mock_open, patch

from src.util import waf_manager


class TestWAFManager(unittest.TestCase):
    def test_load_waf_rules_returns_rules(self):
        file_data = "SecRule a\n\nSecRule b\n"
        with (
            patch("src.util.waf_manager.ENABLE_WAF", True),
            patch("builtins.open", mock_open(read_data=file_data)),
        ):
            self.assertEqual(waf_manager.load_waf_rules(), ["SecRule a", "SecRule b"])

    def test_load_waf_rules_missing_file_returns_empty_list(self):
        with (
            patch("src.util.waf_manager.ENABLE_WAF", True),
            patch("builtins.open", side_effect=FileNotFoundError),
        ):
            self.assertEqual(waf_manager.load_waf_rules(), [])

    def test_reload_waf_rules_writes_rules_and_reloads_nginx(self):
        with (
            patch("src.util.waf_manager.ENABLE_WAF", True),
            patch("builtins.open", mock_open()) as mocked_open,
            patch("src.util.waf_manager.subprocess.run") as mock_run,
        ):
            self.assertTrue(waf_manager.reload_waf_rules(["SecRule one", "SecRule two"]))
            mocked_open().write.assert_called_once_with("SecRule one\nSecRule two\n")
            mock_run.assert_called_once_with(waf_manager.NGINX_RELOAD_CMD, check=True)

    def test_reload_waf_rules_returns_false_on_reload_failure(self):
        with (
            patch("src.util.waf_manager.ENABLE_WAF", True),
            patch("builtins.open", mock_open()),
            patch(
                "src.util.waf_manager.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, ["nginx"]),
            ),
        ):
            self.assertFalse(waf_manager.reload_waf_rules(["SecRule one"]))

    def test_reload_waf_rules_returns_false_when_disabled(self):
        with patch("src.util.waf_manager.ENABLE_WAF", False):
            self.assertFalse(waf_manager.reload_waf_rules(["SecRule one"]))

    def test_is_xml_request_delegates_to_xml_validator(self):
        self.assertTrue(waf_manager.is_xml_request("application/xml"))
        self.assertTrue(waf_manager.is_xml_request("application/soap+xml"))
        self.assertFalse(waf_manager.is_xml_request("application/json"))
        self.assertFalse(waf_manager.is_xml_request(None))


if __name__ == "__main__":
    unittest.main()
