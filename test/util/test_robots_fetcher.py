# test/util/robots_fetcher.test.py
import os
import unittest
from unittest.mock import ANY, MagicMock, mock_open, patch

from src.util import robots_fetcher

# Define a base mock exception class for when the real one isn't available


class MockKubeApiException(Exception):
    def __init__(self, status=0):
        self.status = status


# Conditionally import kubernetes for environments where it is available
try:
    from kubernetes.client.rest import ApiException as KubeApiException

    from kubernetes import client, config

    KUBE_AVAILABLE = True
except ImportError:
    KUBE_AVAILABLE = False
    # If kubernetes is not installed, use our mock class for KubeApiException
    KubeApiException = MockKubeApiException
    client = MagicMock()
    config = MagicMock()


class MockResponse:
    def __init__(self, text, status_code):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise robots_fetcher.requests.exceptions.HTTPError()


class TestRobotsFetcherComprehensive(unittest.TestCase):

    def setUp(self):
        # Patch external dependencies
        self.patches = {
            "requests.get": patch("src.util.robots_fetcher.requests.get"),
            "k8s_config.load_incluster_config": patch(
                "src.util.robots_fetcher.k8s_config.load_incluster_config"
            ),
            "k8s_client.CoreV1Api": patch("src.util.robots_fetcher.client.CoreV1Api"),
            "logger": patch("src.util.robots_fetcher.logger"),
        }
        self.mocks = {name: p.start() for name, p in self.patches.items()}

        self.mock_k8s_api = self.mocks["k8s_client.CoreV1Api"].return_value

    def tearDown(self):
        for p in self.patches.values():
            p.stop()
        # Ensure environment variables from tests don't leak
        if "TARGET_URL" in os.environ:
            del os.environ["TARGET_URL"]
        if "KUBERNETES_SERVICE_HOST" in os.environ:
            del os.environ["KUBERNETES_SERVICE_HOST"]

    def test_get_default_robots_txt(self):
        """Test that the default robots.txt content is correct."""
        default_content = robots_fetcher.get_default_robots_txt()
        self.assertIn("User-agent: *", default_content)
        self.assertIn("Disallow: /", default_content)

    def test_fetch_robots_txt_success(self):
        """Test successful fetching and returning of robots.txt content."""
        self.mocks["requests.get"].return_value = MockResponse(
            "User-agent: TestBot\nDisallow: /test/", 200
        )
        content = robots_fetcher.fetch_robots_txt("http://example.com")
        self.assertEqual(content, "User-agent: TestBot\nDisallow: /test/")
        self.mocks["requests.get"].assert_called_with(
            "http://example.com/robots.txt",
            headers=ANY,
            timeout=ANY,
            allow_redirects=False,
        )

    def test_fetch_robots_txt_http_error_returns_default(self):
        """Test that an HTTP error during fetch returns the default content."""
        self.mocks["requests.get"].return_value = MockResponse("Not Found", 404)
        content = robots_fetcher.fetch_robots_txt("http://example.com")
        self.assertEqual(content, robots_fetcher.get_default_robots_txt())
        self.mocks["logger"].error.assert_called_once()

    def test_fetch_robots_txt_connection_error_returns_default(self):
        """Test that a connection error during fetch returns the default content."""
        self.mocks["requests.get"].side_effect = (
            robots_fetcher.requests.exceptions.RequestException("Timeout")
        )
        content = robots_fetcher.fetch_robots_txt("http://example.com")
        self.assertEqual(content, robots_fetcher.get_default_robots_txt())
        self.mocks["logger"].error.assert_called_once()
        self.assertIn(
            "Failed to fetch robots.txt", self.mocks["logger"].error.call_args[0][0]
        )

    def test_fetch_robots_txt_disallowed_scheme_returns_default(self):
        """URLs without http/https schemes return default content."""
        content = robots_fetcher.fetch_robots_txt("ftp://example.com")
        self.assertEqual(content, robots_fetcher.get_default_robots_txt())
        self.mocks["requests.get"].assert_not_called()
        self.mocks["logger"].error.assert_called_once()

    def test_fetch_robots_txt_disallowed_host_returns_default(self):
        """Hosts not in the allowlist return default content."""
        content = robots_fetcher.fetch_robots_txt(
            "http://example.com", allowed_hosts=["allowed.com"]
        )
        self.assertEqual(content, robots_fetcher.get_default_robots_txt())
        self.mocks["requests.get"].assert_not_called()
        self.mocks["logger"].error.assert_called_once()

    def test_fetch_robots_txt_redirect_returns_default(self):
        """Redirect responses should result in default robots.txt content."""
        self.mocks["requests.get"].return_value = MockResponse("", 302)
        content = robots_fetcher.fetch_robots_txt("http://example.com")
        self.assertEqual(content, robots_fetcher.get_default_robots_txt())
        self.mocks["logger"].warning.assert_called_once()
        self.assertIn("Redirect", self.mocks["logger"].warning.call_args[0][0])

    @unittest.skipIf(not KUBE_AVAILABLE, "Kubernetes library not installed")
    def test_update_configmap_patches_existing(self):
        """Test that an existing ConfigMap is patched."""
        self.mock_k8s_api.read_namespaced_config_map.return_value = (
            MagicMock()
        )  # Simulate CM exists

        robots_fetcher.update_configmap(self.mock_k8s_api, "new content")

        self.mock_k8s_api.patch_namespaced_config_map.assert_called_once()
        body = self.mock_k8s_api.patch_namespaced_config_map.call_args[1]["body"]
        self.assertEqual(body.data["robots.txt"], "new content")
        self.mock_k8s_api.create_namespaced_config_map.assert_not_called()

    @unittest.skipIf(not KUBE_AVAILABLE, "Kubernetes library not installed")
    def test_update_configmap_creates_new(self):
        """Test that a new ConfigMap is created if it doesn't exist."""
        self.mock_k8s_api.patch_namespaced_config_map.side_effect = KubeApiException(
            status=404
        )

        robots_fetcher.update_configmap(self.mock_k8s_api, "new content")

        self.mock_k8s_api.create_namespaced_config_map.assert_called_once()
        body = self.mock_k8s_api.create_namespaced_config_map.call_args[1]["body"]
        self.assertEqual(body.data["robots.txt"], "new content")
        self.mock_k8s_api.patch_namespaced_config_map.assert_called_once()

    @unittest.skipIf(not KUBE_AVAILABLE, "Kubernetes library not installed")
    @patch("src.util.robots_fetcher.get_kubernetes_api")
    @patch("src.util.robots_fetcher.fetch_robots_txt")
    @patch("src.util.robots_fetcher.update_configmap")
    def test_main_flow_in_cluster(self, mock_update_cm, mock_fetch, mock_get_api):
        """Test the main execution logic when running inside a Kubernetes cluster."""
        mock_get_api.return_value = self.mock_k8s_api
        mock_fetch.return_value = "fetched content"

        with patch.dict(
            os.environ,
            {"KUBERNETES_SERVICE_HOST": "yes", "TARGET_URL": "http://target.com"},
        ):
            robots_fetcher._run_as_script()

        mock_get_api.assert_called_once_with()
        mock_fetch.assert_called_once_with("http://target.com")
        mock_update_cm.assert_called_once_with(self.mock_k8s_api, "fetched content")

    def test_main_flow_local_mode(self):
        """Test the main execution logic when not in a cluster (local mode)."""
        with patch.dict(os.environ, {}, clear=True), patch(
            "builtins.open", mock_open()
        ) as mock_file:
            # Set TARGET_URL for local execution
            os.environ["TARGET_URL"] = "http://localtarget.com"
            self.mocks["requests.get"].return_value = MockResponse("local content", 200)

            robots_fetcher._run_as_script()

            mock_file.assert_called_with(ANY, "w", encoding="utf-8")
            mock_file().write.assert_called_once_with("local content")
            # Ensure k8s functions were not called
            self.mocks["k8s_config.load_incluster_config"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
