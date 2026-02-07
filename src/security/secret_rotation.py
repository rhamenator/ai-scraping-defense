"""
Automated secret rotation service for managing secret lifecycle and rotation.

This module provides functionality to automatically rotate secrets stored in
HashiCorp Vault, update dependent services, and maintain an audit trail of
rotation activities.
"""

import logging
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from src.shared.vault_client import VaultClient, get_vault_client

logger = logging.getLogger(__name__)


@dataclass
class SecretRotationPolicy:
    """Policy defining how and when a secret should be rotated."""

    name: str
    path: str
    rotation_period_days: int
    key_name: str = "value"
    min_length: int = 32
    include_uppercase: bool = True
    include_lowercase: bool = True
    include_digits: bool = True
    include_special: bool = True
    custom_generator: Optional[Callable[[], str]] = None
    pre_rotation_hook: Optional[Callable[[str, str], None]] = None
    post_rotation_hook: Optional[Callable[[str, str], None]] = None
    mount_point: str = "secret"


class SecretRotationService:
    """Service for automated secret rotation and lifecycle management."""

    def __init__(self, vault_client: Optional[VaultClient] = None):
        """
        Initialize the secret rotation service.

        Args:
            vault_client: VaultClient instance. If None, uses global client.
        """
        self.vault_client = vault_client or get_vault_client()
        if not self.vault_client:
            raise ValueError("Vault client is required for secret rotation")

    def generate_secret(self, policy: SecretRotationPolicy) -> str:
        """
        Generate a new secret value according to policy.

        Args:
            policy: Rotation policy defining requirements

        Returns:
            Generated secret string
        """
        if policy.custom_generator:
            return policy.custom_generator()

        # Build character set based on policy
        chars = ""
        if policy.include_lowercase:
            chars += string.ascii_lowercase
        if policy.include_uppercase:
            chars += string.ascii_uppercase
        if policy.include_digits:
            chars += string.digits
        if policy.include_special:
            chars += "!@#$%^&*()-_=+[]{}|;:,.<>?"

        if not chars:
            raise ValueError("At least one character type must be enabled")

        # Generate secret
        secret_value = "".join(secrets.choice(chars) for _ in range(policy.min_length))

        # Ensure at least one character from each required type
        if policy.include_uppercase and not any(c.isupper() for c in secret_value):
            pos = secrets.randbelow(len(secret_value))
            secret_value = (
                secret_value[:pos]
                + secrets.choice(string.ascii_uppercase)
                + secret_value[pos + 1 :]
            )

        if policy.include_lowercase and not any(c.islower() for c in secret_value):
            pos = secrets.randbelow(len(secret_value))
            secret_value = (
                secret_value[:pos]
                + secrets.choice(string.ascii_lowercase)
                + secret_value[pos + 1 :]
            )

        if policy.include_digits and not any(c.isdigit() for c in secret_value):
            pos = secrets.randbelow(len(secret_value))
            secret_value = (
                secret_value[:pos]
                + secrets.choice(string.digits)
                + secret_value[pos + 1 :]
            )

        if policy.include_special and not any(
            c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in secret_value
        ):
            pos = secrets.randbelow(len(secret_value))
            secret_value = (
                secret_value[:pos]
                + secrets.choice("!@#$%^&*()-_=+[]{}|;:,.<>?")
                + secret_value[pos + 1 :]
            )

        return secret_value

    def rotate_secret(
        self, policy: SecretRotationPolicy, force: bool = False
    ) -> Dict[str, Any]:
        """
        Rotate a secret according to policy.

        Args:
            policy: Rotation policy
            force: Force rotation even if not due

        Returns:
            Dictionary with rotation details
        """
        result = {
            "success": False,
            "policy_name": policy.name,
            "path": policy.path,
            "rotated": False,
            "message": "",
            "timestamp": datetime.utcnow().isoformat(),
        }

        try:
            # Check if rotation is needed
            if not force:
                metadata = self.vault_client.read_secret_metadata(
                    policy.path, policy.mount_point
                )
                if metadata:
                    created_time = metadata.get("created_time")
                    if created_time:
                        created_dt = datetime.fromisoformat(
                            created_time.replace("Z", "+00:00")
                        )
                        rotation_due = created_dt + timedelta(
                            days=policy.rotation_period_days
                        )
                        if datetime.utcnow() < rotation_due.replace(tzinfo=None):
                            result["message"] = "Rotation not yet due"
                            result["success"] = True
                            return result

            # Read current secret
            current_secret = self.vault_client.read_secret(
                policy.path, mount_point=policy.mount_point
            )
            old_value = current_secret.get(policy.key_name) if current_secret else None

            # Generate new secret
            new_value = self.generate_secret(policy)

            # Execute pre-rotation hook
            if policy.pre_rotation_hook:
                try:
                    policy.pre_rotation_hook(old_value, new_value)
                except Exception as e:
                    result["message"] = f"Pre-rotation hook failed: {e}"
                    logger.error(f"Pre-rotation hook failed for {policy.name}: {e}")
                    return result

            # Write new secret to Vault
            secret_data = current_secret.copy() if current_secret else {}
            secret_data[policy.key_name] = new_value
            secret_data["rotated_at"] = datetime.utcnow().isoformat()
            secret_data["rotation_policy"] = policy.name

            success = self.vault_client.write_secret(
                policy.path, secret_data, mount_point=policy.mount_point
            )

            if not success:
                result["message"] = "Failed to write new secret to Vault"
                return result

            # Execute post-rotation hook
            if policy.post_rotation_hook:
                try:
                    policy.post_rotation_hook(old_value, new_value)
                except Exception as e:
                    result["message"] = f"Post-rotation hook failed: {e}"
                    logger.error(f"Post-rotation hook failed for {policy.name}: {e}")
                    # Note: Secret was written, so we don't return here
                    result["warning"] = str(e)

            result["success"] = True
            result["rotated"] = True
            result["message"] = "Secret rotated successfully"
            logger.info(f"Secret rotated successfully: {policy.name} at {policy.path}")

        except Exception as e:
            result["message"] = f"Error during rotation: {e}"
            logger.error(f"Error rotating secret {policy.name}: {e}")

        return result

    def rotate_multiple(
        self, policies: List[SecretRotationPolicy], force: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Rotate multiple secrets according to their policies.

        Args:
            policies: List of rotation policies
            force: Force rotation even if not due

        Returns:
            List of rotation results
        """
        results = []
        for policy in policies:
            result = self.rotate_secret(policy, force)
            results.append(result)
        return results

    def check_rotation_due(self, policy: SecretRotationPolicy) -> bool:
        """
        Check if a secret is due for rotation.

        Args:
            policy: Rotation policy to check

        Returns:
            True if rotation is due, False otherwise
        """
        try:
            metadata = self.vault_client.read_secret_metadata(
                policy.path, policy.mount_point
            )
            if not metadata:
                return True  # No secret exists, rotation needed

            created_time = metadata.get("created_time")
            if not created_time:
                return True

            created_dt = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
            rotation_due = created_dt + timedelta(days=policy.rotation_period_days)

            return datetime.utcnow() >= rotation_due.replace(tzinfo=None)

        except Exception as e:
            logger.error(f"Error checking rotation due for {policy.name}: {e}")
            return False

    def get_rotation_status(
        self, policies: List[SecretRotationPolicy]
    ) -> List[Dict[str, Any]]:
        """
        Get rotation status for multiple policies.

        Args:
            policies: List of rotation policies

        Returns:
            List of status dictionaries
        """
        status_list = []
        for policy in policies:
            try:
                metadata = self.vault_client.read_secret_metadata(
                    policy.path, policy.mount_point
                )
                if metadata:
                    created_time = metadata.get("created_time")
                    current_version = metadata.get("current_version")
                    versions = metadata.get("versions", {})

                    status = {
                        "policy_name": policy.name,
                        "path": policy.path,
                        "exists": True,
                        "current_version": current_version,
                        "created_time": created_time,
                        "rotation_due": self.check_rotation_due(policy),
                        "total_versions": len(versions),
                    }
                else:
                    status = {
                        "policy_name": policy.name,
                        "path": policy.path,
                        "exists": False,
                        "rotation_due": True,
                    }

                status_list.append(status)

            except Exception as e:
                logger.error(f"Error getting status for {policy.name}: {e}")
                status_list.append(
                    {
                        "policy_name": policy.name,
                        "path": policy.path,
                        "error": str(e),
                    }
                )

        return status_list


def create_default_policies() -> List[SecretRotationPolicy]:
    """
    Create default rotation policies for common secrets.

    Returns:
        List of default rotation policies
    """
    return [
        SecretRotationPolicy(
            name="postgres_password",
            path="database/postgres",
            key_name="password",
            rotation_period_days=90,
            min_length=32,
        ),
        SecretRotationPolicy(
            name="redis_password",
            path="database/redis",
            key_name="password",
            rotation_period_days=90,
            min_length=32,
        ),
        SecretRotationPolicy(
            name="admin_ui_password",
            path="admin/credentials",
            key_name="password",
            rotation_period_days=90,
            min_length=24,
        ),
        SecretRotationPolicy(
            name="system_seed",
            path="system/seed",
            key_name="value",
            rotation_period_days=180,
            min_length=48,
        ),
        SecretRotationPolicy(
            name="jwt_secret",
            path="auth/jwt_secret",
            key_name="value",
            rotation_period_days=90,
            min_length=64,
        ),
    ]
