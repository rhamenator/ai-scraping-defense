"""Feature flag management system."""

import logging
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class FeatureFlagError(Exception):
    """Raised when feature flag operations fail."""

    pass


class RolloutStrategy(str, Enum):
    """Feature rollout strategies."""

    PERCENTAGE = "percentage"
    ALLOWLIST = "allowlist"
    FULL = "full"


class Feature:
    """Represents a single feature flag."""

    def __init__(
        self,
        name: str,
        enabled: bool,
        description: str,
        requires: Optional[List[str]] = None,
    ):
        """
        Initialize a feature flag.

        Args:
            name: Feature name/identifier
            enabled: Whether feature is enabled
            description: Human-readable description
            requires: List of required feature dependencies
        """
        self.name = name
        self.enabled = enabled
        self.description = description
        self.requires = requires or []

    def __repr__(self) -> str:
        status = "enabled" if self.enabled else "disabled"
        return f"Feature({self.name}, {status})"

    def to_dict(self) -> Dict[str, Any]:
        """Export feature as dictionary."""
        return {
            "name": self.name,
            "enabled": self.enabled,
            "description": self.description,
            "requires": self.requires,
        }


class FeatureFlagManager:
    """Manage feature flags with environment-specific overrides."""

    def __init__(
        self,
        config_path: Optional[Path] = None,
        environment: str = "production",
        tenant_id: Optional[str] = None,
    ):
        """
        Initialize feature flag manager.

        Args:
            config_path: Path to features.yaml file
            environment: Current deployment environment
            tenant_id: Optional tenant identifier for multi-tenant support
        """
        self.environment = environment
        self.tenant_id = tenant_id
        self.features: Dict[str, Feature] = {}
        self.rollouts: Dict[str, Dict[str, Any]] = {}

        # Default config path
        if config_path is None:
            config_path = (
                Path(__file__).parent.parent.parent / "config" / "features.yaml"
            )

        self.config_path = config_path
        self._load_features()

    def _load_features(self) -> None:
        """Load features from YAML configuration file."""
        try:
            if not self.config_path.exists():
                logger.warning(
                    "Feature config file not found: %s. Using defaults.",
                    self.config_path,
                )
                self._load_defaults()
                return

            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f)

            # Load base features
            features_config = config.get("features", {})
            for name, feature_data in features_config.items():
                self.features[name] = Feature(
                    name=name,
                    enabled=feature_data.get("enabled", False),
                    description=feature_data.get("description", ""),
                    requires=feature_data.get("requires", []),
                )

            # Apply environment-specific overrides
            env_overrides = (
                config.get("environments", {})
                .get(self.environment, {})
                .get("overrides", {})
            )
            for name, override_data in env_overrides.items():
                if name in self.features:
                    self.features[name].enabled = override_data.get("enabled", False)
                    logger.debug(
                        "Applied environment override for %s in %s: %s",
                        name,
                        self.environment,
                        self.features[name].enabled,
                    )

            # Load rollout configurations
            self.rollouts = config.get("rollouts", {})

            # Validate dependencies
            if config.get("dependency_validation", {}).get("strict", True):
                self._validate_dependencies(
                    auto_disable=config.get("dependency_validation", {}).get(
                        "auto_disable", True
                    )
                )

            logger.info(
                "Loaded %d features for environment: %s",
                len(self.features),
                self.environment,
            )

        except Exception as e:
            logger.error("Failed to load feature flags: %s", e)
            self._load_defaults()

    def _load_defaults(self) -> None:
        """Load minimal default features."""
        defaults = {
            "tarpit_catch_all": True,
            "fingerprinting": True,
            "behavioral_analysis": True,
            "waf_integration": True,
            "prometheus_metrics": True,
            "audit_logging": True,
        }

        for name, enabled in defaults.items():
            self.features[name] = Feature(
                name=name,
                enabled=enabled,
                description=f"Default feature: {name}",
                requires=[],
            )

    def _validate_dependencies(self, auto_disable: bool = True) -> None:
        """
        Validate feature dependencies.

        Args:
            auto_disable: If True, automatically disable features with unmet dependencies.

        Raises:
            FeatureFlagError: If dependencies are invalid and auto_disable is False.
        """
        errors: List[str] = []

        for feature in self.features.values():
            if not feature.enabled:
                continue

            for required in feature.requires:
                if required not in self.features:
                    error = f"Feature '{feature.name}' requires unknown feature '{required}'"
                    errors.append(error)
                    if auto_disable:
                        feature.enabled = False
                        logger.warning("%s. Auto-disabled '%s'.", error, feature.name)
                elif not self.features[required].enabled:
                    error = (
                        f"Feature '{feature.name}' requires '{required}' "
                        f"but it is disabled"
                    )
                    errors.append(error)
                    if auto_disable:
                        feature.enabled = False
                        logger.warning("%s. Auto-disabled '%s'.", error, feature.name)

        if errors and not auto_disable:
            raise FeatureFlagError(
                f"Feature dependency validation failed: {'; '.join(errors)}"
            )

    def is_enabled(self, feature_name: str) -> bool:
        """
        Check if a feature is enabled.

        Args:
            feature_name: Name of the feature to check.

        Returns:
            True if feature is enabled, False otherwise.
        """
        if feature_name not in self.features:
            logger.warning(
                "Unknown feature flag: %s. Defaulting to disabled.", feature_name
            )
            return False

        feature = self.features[feature_name]

        # Check rollout strategy
        if feature_name in self.rollouts:
            rollout = self.rollouts[feature_name]
            strategy = rollout.get("strategy", "full")

            if strategy == "percentage":
                # For percentage rollout, check if tenant is in rollout
                percentage = rollout.get("percentage", 0)
                if percentage < 100 and self.tenant_id:
                    # Simple hash-based rollout
                    tenant_hash = hash(self.tenant_id) % 100
                    if tenant_hash >= percentage:
                        return False

            elif strategy == "allowlist":
                # For allowlist, check if tenant is allowed
                allowed = rollout.get("allowed_tenants", [])
                if self.tenant_id and self.tenant_id not in allowed:
                    return False

        return feature.enabled

    def get_enabled_features(self) -> List[str]:
        """
        Get list of all enabled feature names.

        Returns:
            List of enabled feature names.
        """
        return [name for name, feature in self.features.items() if feature.enabled]

    def get_feature(self, name: str) -> Optional[Feature]:
        """
        Get feature by name.

        Args:
            name: Feature name.

        Returns:
            Feature instance or None if not found.
        """
        return self.features.get(name)

    def get_all_features(self) -> Dict[str, Feature]:
        """
        Get all features.

        Returns:
            Dictionary of all features.
        """
        return self.features.copy()

    def enable_feature(self, feature_name: str) -> None:
        """
        Enable a feature flag.

        Args:
            feature_name: Name of feature to enable.

        Raises:
            FeatureFlagError: If feature doesn't exist or dependencies not met.
        """
        if feature_name not in self.features:
            raise FeatureFlagError(f"Unknown feature: {feature_name}")

        feature = self.features[feature_name]

        # Check dependencies
        for required in feature.requires:
            if required not in self.features or not self.features[required].enabled:
                raise FeatureFlagError(
                    f"Cannot enable '{feature_name}': required feature '{required}' "
                    f"is not enabled"
                )

        feature.enabled = True
        logger.info("Enabled feature: %s", feature_name)

    def disable_feature(self, feature_name: str) -> None:
        """
        Disable a feature flag.

        Args:
            feature_name: Name of feature to disable.

        Raises:
            FeatureFlagError: If feature doesn't exist.
        """
        if feature_name not in self.features:
            raise FeatureFlagError(f"Unknown feature: {feature_name}")

        # Check if other features depend on this one
        dependents = [
            f.name
            for f in self.features.values()
            if feature_name in f.requires and f.enabled
        ]

        if dependents:
            logger.warning(
                "Disabling feature '%s' will affect dependent features: %s",
                feature_name,
                ", ".join(dependents),
            )
            # Auto-disable dependents
            for dependent in dependents:
                self.features[dependent].enabled = False

        self.features[feature_name].enabled = False
        logger.info("Disabled feature: %s", feature_name)

    def export_config(self) -> Dict[str, Any]:
        """
        Export current feature configuration.

        Returns:
            Dictionary representation of all features.
        """
        return {
            "environment": self.environment,
            "tenant_id": self.tenant_id,
            "features": {name: f.to_dict() for name, f in self.features.items()},
            "enabled_count": len(self.get_enabled_features()),
        }


# Global feature flag manager instance
_feature_manager: Optional[FeatureFlagManager] = None


def get_feature_manager(
    environment: Optional[str] = None, tenant_id: Optional[str] = None
) -> FeatureFlagManager:
    """
    Get or create global feature flag manager.

    Args:
        environment: Override environment (default: from APP_ENV env var)
        tenant_id: Override tenant ID (default: from TENANT_ID env var)

    Returns:
        FeatureFlagManager instance.
    """
    global _feature_manager

    import os

    if _feature_manager is None:
        env = environment or os.getenv("APP_ENV", "production")
        tenant = tenant_id or os.getenv("TENANT_ID")
        _feature_manager = FeatureFlagManager(environment=env, tenant_id=tenant)

    return _feature_manager


def is_feature_enabled(feature_name: str) -> bool:
    """
    Check if a feature is enabled (convenience function).

    Args:
        feature_name: Name of feature to check.

    Returns:
        True if enabled, False otherwise.
    """
    return get_feature_manager().is_enabled(feature_name)
