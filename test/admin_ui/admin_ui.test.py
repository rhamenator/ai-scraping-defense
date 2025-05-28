# test/admin_ui/admin_ui.test.py
import unittest
from unittest.mock import patch
import json # For decoding json data

# Assuming admin_ui.py is in the admin_ui directory, and metrics is in the parent.
# The admin_ui.py script handles its own sys.path manipulation for metrics import.
from admin_ui.admin_ui import app # Import the Flask app instance

class TestAdminUI(unittest.TestCase):

    def setUp(self):
        """Set up the test client and other test variables."""
        app.config['TESTING'] = True
        # By default, Flask looks for a 'templates' folder in the same directory as the app module,
        # or in the app's root_path. admin_ui.py is in 'admin_ui/', so it should find 'admin_ui/templates/'.
        # If templates are not found, ensure app.template_folder is correctly set or discoverable.
        self.client = app.test_client()

    def test_index_route_serves_html_and_renders_template(self):
        """Test the '/' route for successful HTML response and basic content."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.content_type)
        
        # Check for some key elements from index.html to confirm it's rendered
        response_data_str = response.data.decode('utf-8')
        self.assertIn("<title>AI Scraping Defense - Admin Dashboard</title>", response_data_str)
        self.assertIn("<h1>Admin Dashboard</h1>", response_data_str)
        self.assertIn('<div id="metrics-display"', response_data_str)
        self.assertIn("fetch('/metrics')", response_data_str, "Expected JavaScript to fetch /metrics")

    @patch("admin_ui.admin_ui.METRICS_AVAILABLE", True)
    @patch("admin_ui.admin_ui.get_metrics") # Patching at the location where it's looked up
    def test_metrics_endpoint_success(self, mock_get_metrics):
        """Test the '/metrics' endpoint when metrics are available and fetching succeeds."""
        mock_get_metrics.return_value = {"requests": 100, "errors": 5, "uptime_seconds": 3600}
        
        response = self.client.get('/metrics')
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response.content_type)
        
        json_data = response.get_json()
        self.assertEqual(json_data, {"requests": 100, "errors": 5, "uptime_seconds": 3600})
        mock_get_metrics.assert_called_once()

    @patch("admin_ui.admin_ui.METRICS_AVAILABLE", False)
    # No need to patch get_metrics if METRICS_AVAILABLE is False, as it won't be called.
    def test_metrics_endpoint_metrics_module_unavailable(self):
        """Test the '/metrics' endpoint when the metrics module is unavailable."""
        response = self.client.get('/metrics')
        self.assertEqual(response.status_code, 500)
        self.assertIn("application/json", response.content_type)
        
        json_data = response.get_json()
        self.assertIn("error", json_data)
        self.assertEqual(json_data["error"], "Metrics module unavailable")

    @patch("admin_ui.admin_ui.METRICS_AVAILABLE", True)
    @patch("admin_ui.admin_ui.get_metrics")
    def test_metrics_endpoint_get_metrics_internal_error(self, mock_get_metrics):
        """Test the '/metrics' endpoint when get_metrics() raises an internal error."""
        mock_get_metrics.side_effect = Exception("Simulated database error")
        
        response = self.client.get('/metrics')
        self.assertEqual(response.status_code, 500)
        self.assertIn("application/json", response.content_type)
        
        json_data = response.get_json()
        self.assertIn("error", json_data)
        self.assertEqual(json_data["error"], "Failed to retrieve metrics")
        mock_get_metrics.assert_called_once()

    def test_metrics_endpoint_default_get_metrics_if_module_failed_import(self):
        """
        Test behavior if the metrics module import failed in admin_ui.py
        and METRICS_AVAILABLE became False, with the dummy get_metrics.
        This scenario is primarily covered by test_metrics_endpoint_metrics_module_unavailable.
        However, if METRICS_AVAILABLE was True but get_metrics points to the dummy,
        that's an inconsistent state not directly testable without modifying admin_ui.py's import logic.
        The current test_metrics_endpoint_metrics_module_unavailable covers the intended path.
        """
        # This test case essentially re-verifies test_metrics_endpoint_metrics_module_unavailable
        # as the METRICS_AVAILABLE=False path is the one that uses the dummy setup.
        with patch("admin_ui.admin_ui.METRICS_AVAILABLE", False):
            # The dummy get_metrics defined in admin_ui.py won't actually be called
            # if METRICS_AVAILABLE is False, because the first check short-circuits.
            response = self.client.get('/metrics')
            self.assertEqual(response.status_code, 500)
            json_data = response.get_json()
            self.assertEqual(json_data["error"], "Metrics module unavailable")

if __name__ == '__main__':
    unittest.main()
