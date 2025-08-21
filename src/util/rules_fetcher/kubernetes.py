import logging
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
