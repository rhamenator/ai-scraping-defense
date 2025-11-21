"""Tests for configuration drift detection."""

import json
import tempfile
import unittest
from pathlib import Path

from src.util.config_drift import ConfigDrift


class TestConfigDrift(unittest.TestCase):
    """Test configuration drift detection."""

    def setUp(self):
        """Set up test fixtures."""
        self.base_config = {
            "metadata": {
                "version": "1.0.0",
                "environment": "production",
            },
            "model_uri": "sklearn:///model.joblib",
            "log_level": "INFO",
            "tenant_id": "default",
            "redis": {
                "host": "redis",
                "port": 6379,
            },
            "tarpit": {
                "min_delay_sec": 0.6,
                "max_delay_sec": 1.2,
            },
        }

    def test_compute_checksum(self):
        """Test checksum computation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            drift = ConfigDrift(baseline_dir=Path(tmpdir))

            checksum1 = drift.compute_checksum(self.base_config)
            checksum2 = drift.compute_checksum(self.base_config)

            # Same config should produce same checksum
            self.assertEqual(checksum1, checksum2)

    def test_checksum_ignores_volatile_fields(self):
        """Test that volatile fields don't affect checksum."""
        with tempfile.TemporaryDirectory() as tmpdir:
            drift = ConfigDrift(baseline_dir=Path(tmpdir))

            config1 = self.base_config.copy()
            config2 = self.base_config.copy()

            # Add volatile metadata fields
            config1["metadata"]["last_validated"] = "2025-01-01T00:00:00"
            config2["metadata"]["last_validated"] = "2025-01-02T00:00:00"

            checksum1 = drift.compute_checksum(config1)
            checksum2 = drift.compute_checksum(config2)

            # Checksums should be the same (volatile fields filtered)
            self.assertEqual(checksum1, checksum2)

    def test_checksum_detects_stable_changes(self):
        """Test that stable field changes affect checksum."""
        with tempfile.TemporaryDirectory() as tmpdir:
            drift = ConfigDrift(baseline_dir=Path(tmpdir))

            config1 = self.base_config.copy()
            config2 = self.base_config.copy()
            config2["log_level"] = "DEBUG"

            checksum1 = drift.compute_checksum(config1)
            checksum2 = drift.compute_checksum(config2)

            # Checksums should be different
            self.assertNotEqual(checksum1, checksum2)

    def test_filter_sensitive_fields(self):
        """Test that sensitive fields are filtered."""
        with tempfile.TemporaryDirectory() as tmpdir:
            drift = ConfigDrift(baseline_dir=Path(tmpdir))

            config = self.base_config.copy()
            config["redis"]["password"] = "secret123"
            config["jwt_secret"] = "jwt_secret_key"

            filtered = drift._filter_volatile_fields(config)

            # Sensitive fields should be removed
            self.assertNotIn("password", filtered.get("redis", {}))
            self.assertNotIn("jwt_secret", filtered)

    def test_save_and_load_baseline(self):
        """Test saving and loading baseline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            drift = ConfigDrift(baseline_dir=Path(tmpdir))

            # Save baseline
            filepath = drift.save_baseline(
                self.base_config, environment="production", version="1.0.0"
            )

            self.assertTrue(filepath.exists())

            # Load baseline
            loaded = drift.load_baseline(environment="production", version="1.0.0")

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["environment"], "production")
            self.assertEqual(loaded["version"], "1.0.0")
            self.assertIn("checksum", loaded)
            self.assertIn("config", loaded)

    def test_load_latest_baseline(self):
        """Test loading latest baseline when version not specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            drift = ConfigDrift(baseline_dir=Path(tmpdir))

            # Save multiple baselines
            drift.save_baseline(self.base_config, environment="production", version="1.0.0")
            drift.save_baseline(self.base_config, environment="production", version="1.1.0")

            # Load latest (should be 1.1.0 due to sorting)
            loaded = drift.load_baseline(environment="production")

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["version"], "1.1.0")

    def test_detect_no_drift(self):
        """Test drift detection with no changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            drift = ConfigDrift(baseline_dir=Path(tmpdir))

            # Save baseline
            drift.save_baseline(self.base_config, environment="production")

            # Check drift (should be none)
            has_drift, changes, details = drift.detect_drift(
                self.base_config, environment="production"
            )

            self.assertFalse(has_drift)
            self.assertEqual(len(changes), 0)

    def test_detect_drift_with_changes(self):
        """Test drift detection with configuration changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            drift = ConfigDrift(baseline_dir=Path(tmpdir))

            # Save baseline
            drift.save_baseline(self.base_config, environment="production")

            # Modify config
            modified_config = self.base_config.copy()
            modified_config["log_level"] = "DEBUG"
            modified_config["tarpit"]["min_delay_sec"] = 1.0

            # Detect drift
            has_drift, changes, details = drift.detect_drift(
                modified_config, environment="production"
            )

            self.assertTrue(has_drift)
            self.assertGreater(len(changes), 0)
            self.assertIn("changes", details)

            # Check that changes are recorded
            change_paths = [c["path"] for c in details["changes"]]
            self.assertIn("log_level", change_paths)
            self.assertIn("tarpit.min_delay_sec", change_paths)

    def test_detect_drift_added_field(self):
        """Test drift detection with added field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            drift = ConfigDrift(baseline_dir=Path(tmpdir))

            drift.save_baseline(self.base_config, environment="production")

            # Add new field
            modified_config = self.base_config.copy()
            modified_config["new_field"] = "new_value"

            has_drift, changes, details = drift.detect_drift(
                modified_config, environment="production"
            )

            self.assertTrue(has_drift)

            # Check for added change
            added_changes = [c for c in details["changes"] if c["type"] == "added"]
            self.assertGreater(len(added_changes), 0)

    def test_detect_drift_removed_field(self):
        """Test drift detection with removed field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            drift = ConfigDrift(baseline_dir=Path(tmpdir))

            drift.save_baseline(self.base_config, environment="production")

            # Remove field
            modified_config = self.base_config.copy()
            modified_config.pop("tenant_id")

            has_drift, changes, details = drift.detect_drift(
                modified_config, environment="production"
            )

            self.assertTrue(has_drift)

            # Check for removed change
            removed_changes = [c for c in details["changes"] if c["type"] == "removed"]
            self.assertGreater(len(removed_changes), 0)

    def test_generate_drift_report(self):
        """Test drift report generation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            drift = ConfigDrift(baseline_dir=Path(tmpdir))

            drift.save_baseline(self.base_config, environment="production")

            modified_config = self.base_config.copy()
            modified_config["log_level"] = "DEBUG"

            has_drift, changes, details = drift.detect_drift(
                modified_config, environment="production"
            )

            # Generate report
            report = drift.generate_drift_report(details)

            self.assertIn("CONFIGURATION DRIFT REPORT", report)
            self.assertIn("MODIFIED", report)
            self.assertIn("log_level", report)

    def test_list_baselines(self):
        """Test listing available baselines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            drift = ConfigDrift(baseline_dir=Path(tmpdir))

            # Save baselines for different environments
            drift.save_baseline(self.base_config, environment="production", version="1.0.0")
            drift.save_baseline(self.base_config, environment="staging", version="1.0.0")

            # List all baselines
            all_baselines = drift.list_baselines()
            self.assertEqual(len(all_baselines), 2)

            # List production baselines only
            prod_baselines = drift.list_baselines(environment="production")
            self.assertEqual(len(prod_baselines), 1)
            self.assertEqual(prod_baselines[0]["environment"], "production")

    def test_no_baseline_returns_false(self):
        """Test drift detection when no baseline exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            drift = ConfigDrift(baseline_dir=Path(tmpdir))

            has_drift, changes, details = drift.detect_drift(
                self.base_config, environment="production"
            )

            # Should return no drift when no baseline exists
            self.assertFalse(has_drift)
            self.assertEqual(len(changes), 0)


if __name__ == "__main__":
    unittest.main()
