# test\admin_ui\admin_ui.test.py
import unittest
from unittest.mock import patch
from flask import Response
from admin_ui import admin_ui


def unpack_response(result):
    # If it's a tuple (Response, status_code), merge status code into response
    if isinstance(result, tuple):
        response, code = result
        response.status_code = code
        return response
    return result


class TestAdminUI(unittest.TestCase):

    def test_index_returns_html_response(self):
        response = unpack_response(admin_ui.index())
        assert isinstance(response, Response)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.content_type)

    @patch("admin_ui.admin_ui.get_metrics", return_value={"requests": 42, "errors": 0})
    @patch("admin_ui.admin_ui.METRICS_AVAILABLE", True)
    def test_metrics_endpoint_success(self, _, __):
        response = unpack_response(admin_ui.metrics_endpoint())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"requests": 42, "errors": 0})

    @patch("admin_ui.admin_ui.METRICS_AVAILABLE", False)
    def test_metrics_endpoint_metrics_unavailable(self):
        response = unpack_response(admin_ui.metrics_endpoint())
        self.assertEqual(response.status_code, 500)
        json_data = response.get_json()
        self.assertIn("error", json_data)
        self.assertIn("unavailable", json_data["error"].lower())

    @patch("admin_ui.admin_ui.get_metrics", side_effect=Exception("DB error"))
    @patch("admin_ui.admin_ui.METRICS_AVAILABLE", True)
    def test_metrics_endpoint_internal_error(self, _, __):
        response = unpack_response(admin_ui.metrics_endpoint())
        self.assertEqual(response.status_code, 500)
        json_data = response.get_json()
        self.assertIn("error", json_data)
        self.assertIn("failed", json_data["error"].lower())


if __name__ == '__main__':
    unittest.main()
