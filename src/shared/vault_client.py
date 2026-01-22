"""
Comprehensive HashiCorp Vault client with support for KV secrets, dynamic credentials,
secret rotation, and lifecycle management.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import hvac
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class VaultConnectionError(Exception):
    """Raised when a Vault connection cannot be established."""


class VaultSecretNotFoundError(Exception):
    """Raised when a requested secret is not found in Vault."""


@dataclass
class VaultConfig:
    """Configuration for Vault client."""

    addr: str
    token: Optional[str] = None
    namespace: Optional[str] = None
    role_id: Optional[str] = None
    secret_id: Optional[str] = None
    mount_point: str = "secret"
    kubernetes_role: Optional[str] = None
    kubernetes_jwt_path: str = "/var/run/secrets/kubernetes.io/serviceaccount/token"
    verify_tls: bool = True
    timeout: int = 30

    @classmethod
    def from_env(cls) -> "VaultConfig":
        """Load Vault configuration from environment variables."""
        vault_scheme = os.getenv("VAULT_SCHEME", "http")
        return cls(
            addr=os.getenv("VAULT_ADDR") or f"{vault_scheme}://vault:8200",
            token=os.getenv("VAULT_TOKEN"),
            namespace=os.getenv("VAULT_NAMESPACE"),
            role_id=os.getenv("VAULT_ROLE_ID"),
            secret_id=os.getenv("VAULT_SECRET_ID"),
            mount_point=os.getenv("VAULT_MOUNT_POINT", "secret"),
            kubernetes_role=os.getenv("VAULT_KUBERNETES_ROLE"),
            kubernetes_jwt_path=os.getenv(
                "VAULT_KUBERNETES_JWT_PATH",
                "/var/run/secrets/kubernetes.io/serviceaccount/token",
            ),
            verify_tls=os.getenv("VAULT_VERIFY_TLS", "true").lower() == "true",
            timeout=int(os.getenv("VAULT_TIMEOUT", "30")),
        )


class VaultClient:
    """
    Enhanced Vault client with support for multiple authentication methods,
    secret versioning, and lifecycle management.
    """

    def __init__(self, config: Optional[VaultConfig] = None):
        """
        Initialize Vault client with configuration.

        Args:
            config: VaultConfig instance. If None, loads from environment.
        """
        self.config = config or VaultConfig.from_env()
        self._client: Optional[hvac.Client] = None
        self._authenticated = False

    @property
    def client(self) -> hvac.Client:
        """Get or create authenticated Vault client."""
        if self._client is None or not self._authenticated:
            self._client = self._create_client()
            self._authenticate()
        return self._client

    def _create_client(self) -> hvac.Client:
        """Create Vault client instance."""
        return hvac.Client(
            url=self.config.addr,
            namespace=self.config.namespace,
            verify=self.config.verify_tls,
            timeout=self.config.timeout,
        )

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=10), stop=stop_after_attempt(3)
    )
    def _authenticate(self) -> None:
        """
        Authenticate with Vault using available credentials.
        Tries methods in order: token, AppRole, Kubernetes.
        """
        if not self._client:
            raise VaultConnectionError("Client not initialized")

        # Method 1: Token authentication
        if self.config.token:
            self._client.token = self.config.token
            try:
                if self._client.is_authenticated():
                    self._authenticated = True
                    logger.info("Vault authenticated with token")
                    return
            except Exception as e:
                logger.warning(f"Token authentication failed: {e}")

        # Method 2: AppRole authentication
        if self.config.role_id and self.config.secret_id:
            try:
                auth_response = self._client.auth.approle.login(
                    role_id=self.config.role_id, secret_id=self.config.secret_id
                )
                self._client.token = auth_response["auth"]["client_token"]
                self._authenticated = True
                logger.info("Vault authenticated with AppRole")
                return
            except Exception as e:
                logger.warning(f"AppRole authentication failed: {e}")

        # Method 3: Kubernetes authentication
        if self.config.kubernetes_role:
            try:
                if os.path.exists(self.config.kubernetes_jwt_path):
                    with open(self.config.kubernetes_jwt_path, "r") as f:
                        jwt = f.read().strip()
                    auth_response = self._client.auth.kubernetes.login(
                        role=self.config.kubernetes_role, jwt=jwt
                    )
                    self._client.token = auth_response["auth"]["client_token"]
                    self._authenticated = True
                    logger.info("Vault authenticated with Kubernetes")
                    return
            except Exception as e:
                logger.warning(f"Kubernetes authentication failed: {e}")

        raise VaultConnectionError(
            "Failed to authenticate with Vault using any available method"
        )

    def is_authenticated(self) -> bool:
        """Check if client is authenticated with Vault."""
        try:
            return self.client.is_authenticated()
        except Exception as e:
            logger.error(f"Failed to check Vault authentication: {e}")
            return False

    def read_secret(
        self,
        path: str,
        version: Optional[int] = None,
        mount_point: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Read a secret from Vault KV v2 store.

        Args:
            path: Path to the secret (e.g., 'myapp/database')
            version: Specific version to read (None for latest)
            mount_point: KV mount point (defaults to config)

        Returns:
            Secret data dictionary or None if not found
        """
        mount = mount_point or self.config.mount_point
        try:
            response = self.client.secrets.kv.v2.read_secret_version(
                path=path, version=version, mount_point=mount
            )
            return response["data"]["data"]
        except hvac.exceptions.InvalidPath:
            logger.warning(f"Secret not found at {mount}/{path}")
            return None
        except Exception as e:
            logger.error(f"Failed to read secret from Vault at {mount}/{path}: {e}")
            return None

    def read_secret_metadata(
        self, path: str, mount_point: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Read secret metadata including version history and custom metadata.

        Args:
            path: Path to the secret
            mount_point: KV mount point (defaults to config)

        Returns:
            Metadata dictionary or None if not found
        """
        mount = mount_point or self.config.mount_point
        try:
            response = self.client.secrets.kv.v2.read_secret_metadata(
                path=path, mount_point=mount
            )
            return response["data"]
        except hvac.exceptions.InvalidPath:
            logger.warning(f"Secret metadata not found at {mount}/{path}")
            return None
        except Exception as e:
            logger.error(f"Failed to read secret metadata from Vault: {e}")
            return None

    def write_secret(
        self,
        path: str,
        data: Dict[str, Any],
        mount_point: Optional[str] = None,
        cas: Optional[int] = None,
    ) -> bool:
        """
        Write a secret to Vault KV v2 store.

        Args:
            path: Path to the secret
            data: Secret data to write
            mount_point: KV mount point (defaults to config)
            cas: Check-and-set version number for optimistic locking

        Returns:
            True if successful, False otherwise
        """
        mount = mount_point or self.config.mount_point
        try:
            self.client.secrets.kv.v2.create_or_update_secret(
                path=path, secret=data, mount_point=mount, cas=cas
            )
            logger.info(f"Secret written to Vault at {mount}/{path}")
            return True
        except Exception as e:
            logger.error(f"Failed to write secret to Vault at {mount}/{path}: {e}")
            return False

    def delete_secret(
        self,
        path: str,
        versions: Optional[List[int]] = None,
        mount_point: Optional[str] = None,
    ) -> bool:
        """
        Delete specific versions of a secret (soft delete).

        Args:
            path: Path to the secret
            versions: List of versions to delete (None for latest)
            mount_point: KV mount point (defaults to config)

        Returns:
            True if successful, False otherwise
        """
        mount = mount_point or self.config.mount_point
        try:
            if versions:
                self.client.secrets.kv.v2.delete_secret_versions(
                    path=path, versions=versions, mount_point=mount
                )
            else:
                self.client.secrets.kv.v2.delete_latest_version_of_secret(
                    path=path, mount_point=mount
                )
            logger.info(f"Secret deleted from Vault at {mount}/{path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete secret from Vault at {mount}/{path}: {e}")
            return False

    def destroy_secret(
        self, path: str, versions: List[int], mount_point: Optional[str] = None
    ) -> bool:
        """
        Permanently destroy specific versions of a secret.

        Args:
            path: Path to the secret
            versions: List of versions to destroy
            mount_point: KV mount point (defaults to config)

        Returns:
            True if successful, False otherwise
        """
        mount = mount_point or self.config.mount_point
        try:
            self.client.secrets.kv.v2.destroy_secret_versions(
                path=path, versions=versions, mount_point=mount
            )
            logger.info(f"Secret versions destroyed at {mount}/{path}: {versions}")
            return True
        except Exception as e:
            logger.error(f"Failed to destroy secret versions: {e}")
            return False

    def list_secrets(
        self, path: str = "", mount_point: Optional[str] = None
    ) -> Optional[List[str]]:
        """
        List secrets at a given path.

        Args:
            path: Path to list (empty for root)
            mount_point: KV mount point (defaults to config)

        Returns:
            List of secret names or None if error
        """
        mount = mount_point or self.config.mount_point
        try:
            response = self.client.secrets.kv.v2.list_secrets(
                path=path, mount_point=mount
            )
            return response["data"]["keys"]
        except hvac.exceptions.InvalidPath:
            return []
        except Exception as e:
            logger.error(f"Failed to list secrets from Vault at {mount}/{path}: {e}")
            return None

    def get_secret_value(
        self,
        path: str,
        key: str,
        version: Optional[int] = None,
        mount_point: Optional[str] = None,
    ) -> Optional[str]:
        """
        Convenience method to get a single secret value.

        Args:
            path: Path to the secret
            key: Key within the secret data
            version: Specific version to read
            mount_point: KV mount point (defaults to config)

        Returns:
            Secret value as string or None if not found
        """
        secret_data = self.read_secret(path, version, mount_point)
        if secret_data:
            return secret_data.get(key)
        return None

    def renew_token(self, increment: Optional[int] = None) -> bool:
        """
        Renew the current Vault token.

        Args:
            increment: TTL increment in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.auth.token.renew_self(increment=increment)
            logger.info("Vault token renewed successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to renew Vault token: {e}")
            return False

    def get_token_ttl(self) -> Optional[int]:
        """
        Get the remaining TTL of the current token.

        Returns:
            TTL in seconds or None if error
        """
        try:
            response = self.client.auth.token.lookup_self()
            return response["data"]["ttl"]
        except Exception as e:
            logger.error(f"Failed to get token TTL: {e}")
            return None

    def close(self) -> None:
        """Close the Vault client connection."""
        if self._client:
            self._client.adapter.close()
            self._client = None
            self._authenticated = False


# Global client instance (initialized on first use)
_vault_client: Optional[VaultClient] = None


def get_vault_client() -> Optional[VaultClient]:
    """
    Get or create the global Vault client instance.

    Returns:
        VaultClient instance or None if Vault is not configured
    """
    global _vault_client

    # Check if Vault is enabled
    if not os.getenv("VAULT_ADDR"):
        return None

    if _vault_client is None:
        try:
            _vault_client = VaultClient()
            if not _vault_client.is_authenticated():
                logger.warning("Vault client created but not authenticated")
                _vault_client = None
        except Exception as e:
            logger.error(f"Failed to create Vault client: {e}")
            return None

    return _vault_client


def close_vault_client() -> None:
    """Close the global Vault client instance."""
    global _vault_client
    if _vault_client:
        _vault_client.close()
        _vault_client = None
