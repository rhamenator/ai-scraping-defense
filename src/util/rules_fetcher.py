import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from typing import Any, Optional

import requests

from .waf_manager import NGINX_RELOAD_CMD, reload_waf_rules

# --- Kubernetes Library Check ---
try:
    from kubernetes.client.rest import ApiException as ImportedK8sApiException

    from kubernetes import client as k8s_client
    from kubernetes import config as k8s_config

    client = k8s_client
    KUBE_AVAILABLE = True
    K8sApiException = ImportedK8sApiException
except Exception:  # pragma: no cover - kubernetes may not be installed
    KUBE_AVAILABLE = False
    k8s_config = None
    k8s_client = None
    client = None

    class K8sApiException(Exception):
        def __init__(self, status: int = 0):
            self.status = status


# --- Logging and Configuration ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

RULES_URL = os.getenv("RULES_DOWNLOAD_URL", "")
CRS_DOWNLOAD_URL = os.getenv("CRS_DOWNLOAD_URL", "")
CONFIGMAP_NAME = os.getenv("WAF_RULES_CONFIGMAP_NAME", "waf-rules")
CONFIGMAP_NAMESPACE = os.getenv("KUBERNETES_NAMESPACE", "default")
RULES_FILE_NAME = os.getenv("RULES_FILE_NAME", "custom.rules")
WAF_RULES_PATH = os.getenv(
    "WAF_RULES_PATH", f"/etc/nginx/modsecurity/rules/{RULES_FILE_NAME}"
)
MODSEC_DIR = os.getenv("MODSECURITY_DIR", "/etc/nginx/modsecurity")


# --- Core Functions ---
def fetch_rules(url: str) -> str:
    """Download rules content from the given URL."""
    if not url:
        logger.error("No URL provided to fetch rules.")
        return ""

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        logger.info("Successfully fetched rules file.")
        return response.text
    except requests.exceptions.RequestException as exc:
        logger.error("Failed to fetch rules from %s: %s", url, exc)
        return ""


def download_and_extract_crs(url: str, dest_dir: str) -> bool:
    """Download and extract the OWASP Core Rule Set archive."""
    if not url:
        logger.error("No CRS archive URL provided.")
        return False

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        logger.error("Failed to download CRS archive from %s: %s", url, exc)
        return False

    with tempfile.TemporaryDirectory() as tmpdir:
        archive_path = os.path.join(tmpdir, "crs_archive")
        with open(archive_path, "wb") as f:
            f.write(response.content)

        try:
            if url.endswith(".zip"):
                with zipfile.ZipFile(archive_path) as zf:
                    zf.extractall(tmpdir)
            else:
                with tarfile.open(archive_path, "r:gz") as tf:
                    tf.extractall(tmpdir)
        except (tarfile.TarError, zipfile.BadZipFile) as exc:
            logger.error("Failed to extract CRS archive: %s", exc)
            return False

        src_root = None
        for root, dirs, files in os.walk(tmpdir):
            if (
                "crs-setup.conf" in files or "crs-setup.conf.example" in files
            ) and "rules" in dirs:
                src_root = root
                break

        if not src_root:
            logger.error("CRS archive missing expected files.")
            return False

        setup_file = os.path.join(src_root, "crs-setup.conf")
        if not os.path.exists(setup_file):
            setup_file = setup_file + ".example"

        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy(setup_file, os.path.join(dest_dir, "crs-setup.conf"))

        dest_rules = os.path.join(dest_dir, "rules")
        if os.path.exists(dest_rules):
            shutil.rmtree(dest_rules)
        shutil.copytree(os.path.join(src_root, "rules"), dest_rules)

    logger.info("OWASP CRS successfully installed to %s", dest_dir)
    return True


def get_kubernetes_api() -> Optional[Any]:
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


def update_configmap(api: Any, content: str) -> None:
    """Creates or updates a ConfigMap with the rules content."""
    if not KUBE_AVAILABLE:
        return

    body = k8s_client.V1ConfigMap(
        api_version="v1",
        kind="ConfigMap",
        metadata=k8s_client.V1ObjectMeta(name=CONFIGMAP_NAME),
        data={RULES_FILE_NAME: content},
    )
    try:
        api.patch_namespaced_config_map(
            name=CONFIGMAP_NAME, namespace=CONFIGMAP_NAMESPACE, body=body
        )
        logger.info("Successfully patched ConfigMap '%s'.", CONFIGMAP_NAME)
    except K8sApiException as exc:
        if exc.status == 404:
            try:
                api.create_namespaced_config_map(
                    namespace=CONFIGMAP_NAMESPACE, body=body
                )
                logger.info("Successfully created ConfigMap '%s'.", CONFIGMAP_NAME)
            except K8sApiException as create_exc:
                logger.error("Failed to create ConfigMap: %s", create_exc)
        else:
            logger.error("Failed to patch ConfigMap: %s", exc)


def _run_as_script() -> None:
    """Helper to execute the module's main block."""
    logger.info("WAF rules fetcher script started.")

    if CRS_DOWNLOAD_URL:
        logger.info("Fetching OWASP CRS from %s", CRS_DOWNLOAD_URL)
        success = download_and_extract_crs(CRS_DOWNLOAD_URL, MODSEC_DIR)
        if success:
            subprocess.run(NGINX_RELOAD_CMD, check=False)
    else:
        rules_content = fetch_rules(RULES_URL)

        if not rules_content:
            logger.warning("No rules content retrieved. Exiting.")
            return

        if KUBE_AVAILABLE and os.environ.get("KUBERNETES_SERVICE_HOST"):
            logger.info("Running inside Kubernetes. Attempting to update ConfigMap.")
            kube_api = get_kubernetes_api()
            if kube_api:
                update_configmap(kube_api, rules_content)
        else:
            logger.info(
                "Not in Kubernetes or library unavailable. Updating local rules file."
            )
            reload_waf_rules(rules_content.splitlines())

    logger.info("WAF rules fetcher script finished.")


if __name__ == "__main__":
    _run_as_script()
