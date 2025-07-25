# util/robots_fetcher.py
import os
import requests
import logging
from urllib.parse import urlparse, urlunparse
from typing import Optional, Any

# --- Kubernetes Library Check ---
# We only check for the library's existence here to set a flag.
# The actual imports will happen inside the functions that need them.
try:
    from kubernetes import config as k8s_config, client as k8s_client
    from kubernetes.client.rest import ApiException as ImportedK8sApiException

    client = k8s_client
    KUBE_AVAILABLE = True
    K8sApiException = ImportedK8sApiException
except Exception:  # pragma: no cover - kubernetes may not be installed
    KUBE_AVAILABLE = False
    k8s_config = None
    k8s_client = None
    client = None

    class K8sApiException(Exception):
        def __init__(self, status=0):
            self.status = status


# --- Logging and Configuration ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
REAL_BACKEND_HOST = os.getenv("REAL_BACKEND_HOST", "http://example.com")
CONFIGMAP_NAME = os.getenv("ROBOTS_CONFIGMAP_NAME", "live-robots-txt-config")
CONFIGMAP_NAMESPACE = os.getenv("KUBERNETES_NAMESPACE", "default")
FETCHER_USER_AGENT = "RobotsTxtFetcher/1.5 (AI-Scraping-Defense-Stack)"
ROBOTS_OUTPUT_FILE = os.getenv("ROBOTS_OUTPUT_FILE", "robots.txt")


# --- Core Functions ---
def get_default_robots_txt() -> str:
    """Returns a default, restrictive robots.txt content."""
    return "User-agent: *\nDisallow: /"


def fetch_robots_txt(url: Optional[str]) -> str:
    """Fetches the robots.txt file from the given base URL."""
    if not url:
        logger.error("No URL provided to fetch robots.txt.")
        return get_default_robots_txt()
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"

    try:
        parsed_url = urlparse(url)
        robots_url = urlunparse(
            (parsed_url.scheme, parsed_url.netloc, "robots.txt", "", "", "")
        )
    except ValueError:
        logger.error(f"Invalid URL provided: {url}")
        return get_default_robots_txt()

    logger.info(f"Attempting to fetch robots.txt from: {robots_url}")
    try:
        response = requests.get(
            robots_url, headers={"User-Agent": FETCHER_USER_AGENT}, timeout=10
        )
        response.raise_for_status()
        logger.info("Successfully fetched robots.txt.")
        return response.text
    except requests.exceptions.RequestException as e:
        logger.error(
            f"Failed to fetch robots.txt from {robots_url}: {e}. Falling back to default."
        )
        return get_default_robots_txt()


def get_kubernetes_api() -> "Optional[Any]":
    """Initializes and returns the Kubernetes CoreV1Api client."""
    if not KUBE_AVAILABLE:
        return None

    try:
        k8s_config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes configuration.")
    except k8s_config.ConfigException:
        try:
            k8s_config.load_kube_config()
            logger.info("Loaded local kube-config file.")
        except k8s_config.ConfigException:
            logger.error("Could not configure Kubernetes client.")
            return None
    return k8s_client.CoreV1Api()


def update_configmap(api: Any, content: str):
    """Creates or updates a ConfigMap in Kubernetes."""
    if not KUBE_AVAILABLE:
        return

    body = k8s_client.V1ConfigMap(
        api_version="v1",
        kind="ConfigMap",
        metadata=k8s_client.V1ObjectMeta(name=CONFIGMAP_NAME),
        data={"robots.txt": content},
    )
    try:
        api.patch_namespaced_config_map(
            name=CONFIGMAP_NAME, namespace=CONFIGMAP_NAMESPACE, body=body
        )
        logger.info(f"Successfully patched ConfigMap '{CONFIGMAP_NAME}'.")
    except K8sApiException as e:
        if e.status == 404:
            try:
                api.create_namespaced_config_map(
                    namespace=CONFIGMAP_NAMESPACE, body=body
                )
                logger.info(f"Successfully created ConfigMap '{CONFIGMAP_NAME}'.")
            except K8sApiException as e_create:
                logger.error(f"Failed to create ConfigMap: {e_create}")
        else:
            logger.error(f"Failed to patch ConfigMap: {e}")


def _run_as_script() -> None:
    """Helper to execute the module's main block. Exposed for tests."""
    logger.info("Robots.txt Fetcher script started.")
    target_url = os.getenv("TARGET_URL", REAL_BACKEND_HOST)
    robots_content = fetch_robots_txt(target_url)

    if KUBE_AVAILABLE and os.environ.get("KUBERNETES_SERVICE_HOST"):
        logger.info("Running inside Kubernetes. Attempting to update ConfigMap.")
        kube_api = get_kubernetes_api()
        if kube_api:
            update_configmap(kube_api, robots_content)
    else:
        logger.info(
            "Not in Kubernetes or library unavailable. Skipping ConfigMap update."
        )
        with open(ROBOTS_OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(robots_content)
        print("\n--- Fetched Robots.txt Content ---")
        print(robots_content)

    logger.info("Robots.txt Fetcher script finished.")


if __name__ == "__main__":
    _run_as_script()
