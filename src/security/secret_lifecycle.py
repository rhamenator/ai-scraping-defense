"""
Secret lifecycle management for tracking secret usage, expiration, and compliance.

This module provides functionality to manage the lifecycle of secrets including
version tracking, expiration monitoring, and automated cleanup.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src.shared.vault_client import VaultClient, get_vault_client

logger = logging.getLogger(__name__)


@dataclass
class SecretLifecycleConfig:
    """Configuration for secret lifecycle management."""

    path: str
    max_versions: int = 10
    expiration_days: Optional[int] = None
    deprecation_warning_days: int = 30
    auto_cleanup: bool = True
    mount_point: str = "secret"


class SecretLifecycleManager:
    """Manager for secret lifecycle operations."""

    def __init__(self, vault_client: Optional[VaultClient] = None):
        """
        Initialize the lifecycle manager.

        Args:
            vault_client: VaultClient instance. If None, uses global client.
        """
        self.vault_client = vault_client or get_vault_client()
        if not self.vault_client:
            raise ValueError("Vault client is required for lifecycle management")

    def get_secret_age(
        self, path: str, mount_point: str = "secret"
    ) -> Optional[timedelta]:
        """
        Get the age of the current secret version.

        Args:
            path: Path to the secret
            mount_point: KV mount point

        Returns:
            Timedelta representing age or None if error
        """
        try:
            metadata = self.vault_client.read_secret_metadata(path, mount_point)
            if not metadata:
                return None

            created_time = metadata.get("created_time")
            if not created_time:
                return None

            created_dt = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
            age = datetime.utcnow() - created_dt.replace(tzinfo=None)
            return age

        except Exception as e:
            logger.error(f"Error getting secret age for {path}: {e}")
            return None

    def is_expired(
        self, path: str, expiration_days: int, mount_point: str = "secret"
    ) -> bool:
        """
        Check if a secret has expired.

        Args:
            path: Path to the secret
            expiration_days: Number of days until expiration
            mount_point: KV mount point

        Returns:
            True if expired, False otherwise
        """
        age = self.get_secret_age(path, mount_point)
        if age is None:
            return False

        return age.days >= expiration_days

    def is_deprecation_warning(
        self,
        path: str,
        expiration_days: int,
        warning_days: int = 30,
        mount_point: str = "secret",
    ) -> bool:
        """
        Check if a secret is approaching expiration.

        Args:
            path: Path to the secret
            expiration_days: Number of days until expiration
            warning_days: Days before expiration to start warning
            mount_point: KV mount point

        Returns:
            True if in warning period, False otherwise
        """
        age = self.get_secret_age(path, mount_point)
        if age is None:
            return False

        days_until_expiration = expiration_days - age.days
        return 0 < days_until_expiration <= warning_days

    def cleanup_old_versions(
        self, path: str, keep_versions: int = 10, mount_point: str = "secret"
    ) -> Dict[str, Any]:
        """
        Clean up old versions of a secret, keeping the most recent ones.

        Args:
            path: Path to the secret
            keep_versions: Number of versions to keep
            mount_point: KV mount point

        Returns:
            Dictionary with cleanup results
        """
        result = {
            "success": False,
            "path": path,
            "versions_deleted": [],
            "message": "",
        }

        try:
            metadata = self.vault_client.read_secret_metadata(path, mount_point)
            if not metadata:
                result["message"] = "Secret not found"
                return result

            versions = metadata.get("versions", {})
            if len(versions) <= keep_versions:
                result["success"] = True
                result["message"] = (
                    f"Only {len(versions)} versions exist, no cleanup needed"
                )
                return result

            # Sort versions by version number (oldest first)
            sorted_versions = sorted(
                [int(v) for v in versions.keys() if not versions[v].get("destroyed")]
            )

            # Determine versions to delete (keep the most recent ones)
            versions_to_delete = sorted_versions[:-keep_versions]

            if versions_to_delete:
                # Soft delete old versions
                success = self.vault_client.delete_secret(
                    path, versions=versions_to_delete, mount_point=mount_point
                )

                if success:
                    result["success"] = True
                    result["versions_deleted"] = versions_to_delete
                    result["message"] = (
                        f"Deleted {len(versions_to_delete)} old versions"
                    )
                    logger.info(
                        f"Cleaned up {len(versions_to_delete)} versions from {path}"
                    )
                else:
                    result["message"] = "Failed to delete versions"
            else:
                result["success"] = True
                result["message"] = "No versions to delete"

        except Exception as e:
            result["message"] = f"Error during cleanup: {e}"
            logger.error(f"Error cleaning up versions for {path}: {e}")

        return result

    def get_lifecycle_status(self, config: SecretLifecycleConfig) -> Dict[str, Any]:
        """
        Get comprehensive lifecycle status for a secret.

        Args:
            config: Lifecycle configuration

        Returns:
            Dictionary with lifecycle status
        """
        status = {
            "path": config.path,
            "exists": False,
            "current_version": None,
            "total_versions": 0,
            "age_days": None,
            "is_expired": False,
            "is_deprecation_warning": False,
            "needs_cleanup": False,
        }

        try:
            metadata = self.vault_client.read_secret_metadata(
                config.path, config.mount_point
            )
            if not metadata:
                return status

            status["exists"] = True
            status["current_version"] = metadata.get("current_version")

            versions = metadata.get("versions", {})
            status["total_versions"] = len(versions)

            # Calculate age
            age = self.get_secret_age(config.path, config.mount_point)
            if age:
                status["age_days"] = age.days

                # Check expiration if configured
                if config.expiration_days:
                    status["is_expired"] = age.days >= config.expiration_days
                    status["is_deprecation_warning"] = self.is_deprecation_warning(
                        config.path,
                        config.expiration_days,
                        config.deprecation_warning_days,
                        config.mount_point,
                    )

            # Check if cleanup is needed
            status["needs_cleanup"] = len(versions) > config.max_versions

            # Add version details
            status["versions"] = {}
            for version_num, version_data in versions.items():
                status["versions"][version_num] = {
                    "created_time": version_data.get("created_time"),
                    "deleted_time": version_data.get("deleted_time"),
                    "destroyed": version_data.get("destroyed", False),
                }

        except Exception as e:
            status["error"] = str(e)
            logger.error(f"Error getting lifecycle status for {config.path}: {e}")

        return status

    def manage_lifecycle(
        self, configs: List[SecretLifecycleConfig]
    ) -> List[Dict[str, Any]]:
        """
        Manage lifecycle for multiple secrets.

        Args:
            configs: List of lifecycle configurations

        Returns:
            List of management results
        """
        results = []

        for config in configs:
            result = {
                "path": config.path,
                "actions": [],
                "status": {},
            }

            try:
                # Get current status
                status = self.get_lifecycle_status(config)
                result["status"] = status

                # Perform cleanup if needed and enabled
                if config.auto_cleanup and status.get("needs_cleanup"):
                    cleanup_result = self.cleanup_old_versions(
                        config.path, config.max_versions, config.mount_point
                    )
                    result["actions"].append(
                        {
                            "type": "cleanup",
                            "result": cleanup_result,
                        }
                    )

                # Add warnings if needed
                if status.get("is_expired"):
                    result["actions"].append(
                        {
                            "type": "warning",
                            "message": f"Secret has expired (age: {status['age_days']} days)",
                            "severity": "critical",
                        }
                    )
                elif status.get("is_deprecation_warning"):
                    days_left = (
                        config.expiration_days - status["age_days"]
                        if config.expiration_days
                        else None
                    )
                    result["actions"].append(
                        {
                            "type": "warning",
                            "message": f"Secret will expire in {days_left} days",
                            "severity": "warning",
                        }
                    )

            except Exception as e:
                result["error"] = str(e)
                logger.error(f"Error managing lifecycle for {config.path}: {e}")

            results.append(result)

        return results

    def get_expiring_secrets(
        self, configs: List[SecretLifecycleConfig], days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get list of secrets that will expire within specified days.

        Args:
            configs: List of lifecycle configurations
            days: Number of days to look ahead

        Returns:
            List of expiring secrets with details
        """
        expiring = []

        for config in configs:
            if not config.expiration_days:
                continue

            try:
                age = self.get_secret_age(config.path, config.mount_point)
                if age:
                    days_until_expiration = config.expiration_days - age.days

                    if 0 < days_until_expiration <= days:
                        expiring.append(
                            {
                                "path": config.path,
                                "age_days": age.days,
                                "days_until_expiration": days_until_expiration,
                                "expiration_days": config.expiration_days,
                            }
                        )

            except Exception as e:
                logger.error(f"Error checking expiration for {config.path}: {e}")

        return expiring


def create_default_lifecycle_configs() -> List[SecretLifecycleConfig]:
    """
    Create default lifecycle configurations for common secrets.

    Returns:
        List of default lifecycle configurations
    """
    return [
        SecretLifecycleConfig(
            path="database/postgres",
            max_versions=10,
            expiration_days=90,
            deprecation_warning_days=14,
        ),
        SecretLifecycleConfig(
            path="database/redis",
            max_versions=10,
            expiration_days=90,
            deprecation_warning_days=14,
        ),
        SecretLifecycleConfig(
            path="admin/credentials",
            max_versions=15,
            expiration_days=90,
            deprecation_warning_days=7,
        ),
        SecretLifecycleConfig(
            path="system/seed",
            max_versions=5,
            expiration_days=180,
            deprecation_warning_days=30,
        ),
        SecretLifecycleConfig(
            path="auth/jwt_secret",
            max_versions=10,
            expiration_days=90,
            deprecation_warning_days=14,
        ),
    ]
