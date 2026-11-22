import logging
from datetime import datetime, timezone
from typing import Any, Optional

from .config import CONFIGMAP_NAME, CONFIGMAP_NAMESPACE, RULES_FILE_NAME

# --- Kubernetes Library Check ---
try:  # pragma: no cover - kubernetes may not be installed
    from kubernetes.client.rest import ApiException as ImportedK8sApiException

    from kubernetes import client as k8s_client
    from kubernetes import config as k8s_config

    KUBE_AVAILABLE = True
    K8sApiException = ImportedK8sApiException
except Exception:  # pragma: no cover - kubernetes may not be installed
    KUBE_AVAILABLE = False
    k8s_config = None  # type: ignore
    k8s_client = None  # type: ignore

    class K8sApiException(Exception):
        def __init__(self, status: int = 0):
            self.status = status


logger = logging.getLogger(__name__)


def _load_kube_config() -> bool:
    try:
        k8s_config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes configuration.")
        return True
    except k8s_config.ConfigException:  # type: ignore[union-attr]
        try:
            k8s_config.load_kube_config()
            logger.info("Loaded local kube-config file.")
            return True
        except k8s_config.ConfigException:  # type: ignore[union-attr]
            logger.error("Could not configure Kubernetes client.")
            return False


def get_apps_api() -> Optional[Any]:
    """Initializes and returns the Kubernetes AppsV1Api client."""
    if not KUBE_AVAILABLE:
        logger.error(
            "The Kubernetes client library is not installed in this image; build one that includes it "
            "(see kubernetes/optional-waf-crs/README.md) or use WAF_RELOAD_MODE=none."
        )
        return None
    if not _load_kube_config():
        return None
    return k8s_client.AppsV1Api()  # type: ignore[union-attr]


def rollout_restart(apps_api: Any, name: str, namespace: str) -> bool:
    """Start a rolling restart of a Deployment, as `kubectl rollout restart` does. Returns True if it was requested."""
    stamp = datetime.now(timezone.utc).isoformat()
    body = {
        "spec": {
            "template": {
                "metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": stamp}}
            }
        }
    }
    try:
        apps_api.patch_namespaced_deployment(name=name, namespace=namespace, body=body)
    except Exception as exc:  # noqa: BLE001 - the API client raises several types; any failure means "not restarted"
        logger.error("Could not restart Deployment '%s' in '%s': %s", name, namespace, exc)
        return False
    logger.info("Requested a rolling restart of Deployment '%s'.", name)
    return True


def get_kubernetes_api() -> Optional[Any]:
    """Initializes and returns the Kubernetes CoreV1Api client."""
    if not KUBE_AVAILABLE:
        return None

    try:
        k8s_config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes configuration.")
    except k8s_config.ConfigException:  # type: ignore[union-attr]
        try:
            k8s_config.load_kube_config()
            logger.info("Loaded local kube-config file.")
        except k8s_config.ConfigException:  # type: ignore[union-attr]
            logger.error("Could not configure Kubernetes client.")
            return None
    return k8s_client.CoreV1Api()  # type: ignore[union-attr]


def update_configmap(api: Any, content: str) -> None:
    """Creates or updates a ConfigMap with the rules content."""
    if not KUBE_AVAILABLE:
        return

    body = k8s_client.V1ConfigMap(  # type: ignore[union-attr]
        api_version="v1",
        kind="ConfigMap",
        metadata=k8s_client.V1ObjectMeta(name=CONFIGMAP_NAME),  # type: ignore[union-attr]
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
