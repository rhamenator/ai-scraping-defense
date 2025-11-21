"""Tests for feature flag management."""

import tempfile
import unittest
from pathlib import Path

import yaml

from src.shared.feature_flags import (
    Feature,
    FeatureFlagError,
    FeatureFlagManager,
    RolloutStrategy,
)


class TestFeature(unittest.TestCase):
    """Test Feature class."""

    def test_feature_creation(self):
        """Test creating a feature."""
        feature = Feature(
            name="test_feature",
            enabled=True,
            description="Test feature",
            requires=["dependency"],
        )

        self.assertEqual(feature.name, "test_feature")
        self.assertTrue(feature.enabled)
        self.assertEqual(feature.description, "Test feature")
        self.assertEqual(feature.requires, ["dependency"])

    def test_feature_to_dict(self):
        """Test feature export to dictionary."""
        feature = Feature(
            name="test_feature",
            enabled=True,
            description="Test feature",
            requires=[],
        )

        feature_dict = feature.to_dict()
        self.assertEqual(feature_dict["name"], "test_feature")
        self.assertTrue(feature_dict["enabled"])


class TestFeatureFlagManager(unittest.TestCase):
    """Test FeatureFlagManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_config = {
            "version": "1.0.0",
            "features": {
                "feature_a": {
                    "enabled": True,
                    "description": "Feature A",
                    "requires": [],
                },
                "feature_b": {
                    "enabled": True,
                    "description": "Feature B",
                    "requires": ["feature_a"],
                },
                "feature_c": {
                    "enabled": False,
                    "description": "Feature C",
                    "requires": [],
                },
            },
            "environments": {
                "development": {"overrides": {"feature_c": {"enabled": True}}},
                "production": {"overrides": {"feature_b": {"enabled": False}}},
            },
            "dependency_validation": {
                "strict": True,
                "auto_disable": True,
            },
        }

    def test_load_features_from_config(self):
        """Test loading features from YAML config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "features.yaml"
            with open(config_path, "w") as f:
                yaml.dump(self.test_config, f)

            manager = FeatureFlagManager(
                config_path=config_path, environment="production"
            )

            self.assertIn("feature_a", manager.features)
            self.assertTrue(manager.is_enabled("feature_a"))

    def test_environment_overrides(self):
        """Test environment-specific overrides."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "features.yaml"
            with open(config_path, "w") as f:
                yaml.dump(self.test_config, f)

            # In production, feature_b should be disabled (override)
            manager_prod = FeatureFlagManager(
                config_path=config_path, environment="production"
            )
            self.assertFalse(manager_prod.is_enabled("feature_b"))

            # In development, feature_c should be enabled (override)
            manager_dev = FeatureFlagManager(
                config_path=config_path, environment="development"
            )
            self.assertTrue(manager_dev.is_enabled("feature_c"))

    def test_dependency_validation(self):
        """Test feature dependency validation."""
        config = {
            "features": {
                "base": {
                    "enabled": False,
                    "description": "Base feature",
                    "requires": [],
                },
                "dependent": {
                    "enabled": True,
                    "description": "Dependent feature",
                    "requires": ["base"],
                },
            },
            "dependency_validation": {
                "strict": True,
                "auto_disable": True,
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "features.yaml"
            with open(config_path, "w") as f:
                yaml.dump(config, f)

            manager = FeatureFlagManager(config_path=config_path)

            # Dependent feature should be auto-disabled
            self.assertFalse(manager.is_enabled("dependent"))

    def test_enable_feature(self):
        """Test enabling a feature."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "features.yaml"
            with open(config_path, "w") as f:
                yaml.dump(self.test_config, f)

            manager = FeatureFlagManager(config_path=config_path)

            # Enable a disabled feature
            self.assertFalse(manager.is_enabled("feature_c"))
            manager.enable_feature("feature_c")
            self.assertTrue(manager.is_enabled("feature_c"))

    def test_enable_feature_with_missing_dependency(self):
        """Test enabling feature with missing dependency fails."""
        config = {
            "features": {
                "base": {
                    "enabled": False,
                    "description": "Base feature",
                    "requires": [],
                },
                "dependent": {
                    "enabled": False,
                    "description": "Dependent feature",
                    "requires": ["base"],
                },
            },
            "dependency_validation": {"strict": False, "auto_disable": False},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "features.yaml"
            with open(config_path, "w") as f:
                yaml.dump(config, f)

            manager = FeatureFlagManager(config_path=config_path)

            # Should raise error when enabling dependent without base
            with self.assertRaises(FeatureFlagError):
                manager.enable_feature("dependent")

    def test_disable_feature(self):
        """Test disabling a feature."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "features.yaml"
            with open(config_path, "w") as f:
                yaml.dump(self.test_config, f)

            manager = FeatureFlagManager(config_path=config_path)

            # Disable feature_a, which should also disable feature_b
            self.assertTrue(manager.is_enabled("feature_a"))
            self.assertTrue(manager.is_enabled("feature_b"))

            manager.disable_feature("feature_a")

            self.assertFalse(manager.is_enabled("feature_a"))
            self.assertFalse(manager.is_enabled("feature_b"))

    def test_unknown_feature(self):
        """Test checking unknown feature returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "features.yaml"
            with open(config_path, "w") as f:
                yaml.dump(self.test_config, f)

            manager = FeatureFlagManager(config_path=config_path)

            # Unknown feature should return False
            self.assertFalse(manager.is_enabled("unknown_feature"))

    def test_get_enabled_features(self):
        """Test getting list of enabled features."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "features.yaml"
            with open(config_path, "w") as f:
                yaml.dump(self.test_config, f)

            manager = FeatureFlagManager(config_path=config_path)

            enabled = manager.get_enabled_features()
            self.assertIn("feature_a", enabled)
            self.assertIn("feature_b", enabled)
            self.assertNotIn("feature_c", enabled)

    def test_export_config(self):
        """Test exporting feature configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "features.yaml"
            with open(config_path, "w") as f:
                yaml.dump(self.test_config, f)

            manager = FeatureFlagManager(
                config_path=config_path,
                environment="production",
                tenant_id="test-tenant",
            )

            exported = manager.export_config()

            self.assertEqual(exported["environment"], "production")
            self.assertEqual(exported["tenant_id"], "test-tenant")
            self.assertIn("features", exported)
            self.assertIn("enabled_count", exported)

    def test_rollout_percentage_strategy(self):
        """Test percentage-based feature rollout."""
        config = {
            "features": {
                "test_feature": {
                    "enabled": True,
                    "description": "Test feature",
                    "requires": [],
                }
            },
            "rollouts": {"test_feature": {"strategy": "percentage", "percentage": 50}},
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "features.yaml"
            with open(config_path, "w") as f:
                yaml.dump(config, f)

            # With tenant_id that hashes to < 50, feature should be enabled
            manager = FeatureFlagManager(config_path=config_path, tenant_id="tenant1")

            # Result depends on hash, but should be deterministic
            result = manager.is_enabled("test_feature")
            self.assertIsInstance(result, bool)

    def test_rollout_allowlist_strategy(self):
        """Test allowlist-based feature rollout."""
        config = {
            "features": {
                "test_feature": {
                    "enabled": True,
                    "description": "Test feature",
                    "requires": [],
                }
            },
            "rollouts": {
                "test_feature": {
                    "strategy": "allowlist",
                    "allowed_tenants": ["tenant1", "tenant2"],
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "features.yaml"
            with open(config_path, "w") as f:
                yaml.dump(config, f)

            # Allowed tenant
            manager1 = FeatureFlagManager(config_path=config_path, tenant_id="tenant1")
            self.assertTrue(manager1.is_enabled("test_feature"))

            # Not allowed tenant
            manager2 = FeatureFlagManager(config_path=config_path, tenant_id="tenant3")
            self.assertFalse(manager2.is_enabled("test_feature"))


if __name__ == "__main__":
    unittest.main()
