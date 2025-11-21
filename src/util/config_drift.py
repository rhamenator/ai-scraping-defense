"""Configuration drift detection and reporting."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ConfigDrift:
    """Track and detect configuration drift."""

    def __init__(self, baseline_dir: Optional[Path] = None):
        """
        Initialize drift detector.

        Args:
            baseline_dir: Directory to store baseline configurations.
                         Defaults to ./data/config_baselines/
        """
        if baseline_dir is None:
            baseline_dir = Path(__file__).parent.parent.parent / "data" / "config_baselines"

        self.baseline_dir = baseline_dir
        self.baseline_dir.mkdir(parents=True, exist_ok=True)

    def compute_checksum(self, config: Dict[str, Any]) -> str:
        """
        Compute checksum of configuration.

        Args:
            config: Configuration dictionary.

        Returns:
            SHA256 hash of configuration.
        """
        # Remove fields that are expected to change
        stable_config = self._filter_volatile_fields(config)
        config_json = json.dumps(stable_config, sort_keys=True)
        return hashlib.sha256(config_json.encode()).hexdigest()

    def _filter_volatile_fields(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter out fields that are expected to change between runs.

        Args:
            config: Original configuration.

        Returns:
            Configuration with volatile fields removed.
        """
        # Create a copy to avoid mutating the original
        filtered = config.copy()

        # Remove metadata fields that change frequently
        if "metadata" in filtered:
            metadata = filtered["metadata"].copy()
            # Keep version, but remove timestamps
            metadata.pop("last_modified", None)
            metadata.pop("last_validated", None)
            filtered["metadata"] = metadata

        # Remove sensitive fields that shouldn't be in baseline
        sensitive_fields = [
            "password",
            "secret",
            "token",
            "api_key",
            "jwt_secret",
            "admin_ui_password_hash",
            "admin_ui_2fa_secret",
        ]

        def remove_sensitive(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {
                    k: remove_sensitive(v)
                    for k, v in obj.items()
                    if not any(sensitive in k.lower() for sensitive in sensitive_fields)
                }
            elif isinstance(obj, list):
                return [remove_sensitive(item) for item in obj]
            else:
                return obj

        return remove_sensitive(filtered)

    def save_baseline(
        self, config: Dict[str, Any], environment: str, version: Optional[str] = None
    ) -> Path:
        """
        Save configuration baseline.

        Args:
            config: Configuration to save as baseline.
            environment: Environment name (dev, staging, prod).
            version: Optional version identifier.

        Returns:
            Path to saved baseline file.
        """
        checksum = self.compute_checksum(config)
        timestamp = datetime.now(timezone.utc).isoformat()

        baseline = {
            "environment": environment,
            "version": version or config.get("metadata", {}).get("version", "unknown"),
            "timestamp": timestamp,
            "checksum": checksum,
            "config": self._filter_volatile_fields(config),
        }

        # Use version or timestamp in filename
        version_str = version or timestamp.replace(":", "-").split(".")[0]
        filename = f"{environment}_{version_str}_baseline.json"
        filepath = self.baseline_dir / filename

        with open(filepath, "w") as f:
            json.dump(baseline, f, indent=2, sort_keys=True)

        logger.info("Saved configuration baseline: %s", filepath)
        return filepath

    def load_baseline(self, environment: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Load configuration baseline.

        Args:
            environment: Environment name.
            version: Optional specific version to load. If None, loads latest.

        Returns:
            Baseline configuration or None if not found.
        """
        if version:
            filename = f"{environment}_{version}_baseline.json"
            filepath = self.baseline_dir / filename
            if filepath.exists():
                with open(filepath, "r") as f:
                    return json.load(f)
            return None
        else:
            # Find latest baseline for environment
            pattern = f"{environment}_*_baseline.json"
            baselines = sorted(self.baseline_dir.glob(pattern), reverse=True)
            if baselines:
                with open(baselines[0], "r") as f:
                    return json.load(f)
            return None

    def detect_drift(
        self, current_config: Dict[str, Any], baseline: Optional[Dict[str, Any]] = None, environment: Optional[str] = None
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Detect configuration drift from baseline.

        Args:
            current_config: Current configuration to check.
            baseline: Baseline configuration to compare against.
                     If None, loads latest baseline for environment.
            environment: Environment name (required if baseline is None).

        Returns:
            Tuple of (has_drift, list_of_changes, drift_details)
        """
        if baseline is None:
            if environment is None:
                raise ValueError("environment required when baseline is None")
            baseline = self.load_baseline(environment)
            if baseline is None:
                logger.warning("No baseline found for environment: %s", environment)
                return False, [], {}

        current_checksum = self.compute_checksum(current_config)
        baseline_checksum = baseline.get("checksum", "")

        if current_checksum == baseline_checksum:
            return False, [], {}

        # Detailed drift analysis
        changes = []
        drift_details = {
            "baseline_checksum": baseline_checksum,
            "current_checksum": current_checksum,
            "baseline_version": baseline.get("version", "unknown"),
            "baseline_timestamp": baseline.get("timestamp", "unknown"),
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "changes": [],
        }

        # Compare configurations recursively
        baseline_config = baseline.get("config", {})
        current_filtered = self._filter_volatile_fields(current_config)

        def compare_dicts(path: str, base: Any, curr: Any) -> None:
            """Recursively compare dictionaries and track changes."""
            if isinstance(base, dict) and isinstance(curr, dict):
                all_keys = set(base.keys()) | set(curr.keys())
                for key in all_keys:
                    new_path = f"{path}.{key}" if path else key
                    if key not in base:
                        change = f"Added: {new_path} = {curr[key]}"
                        changes.append(change)
                        drift_details["changes"].append(
                            {"type": "added", "path": new_path, "value": curr[key]}
                        )
                    elif key not in curr:
                        change = f"Removed: {new_path}"
                        changes.append(change)
                        drift_details["changes"].append(
                            {"type": "removed", "path": new_path, "old_value": base[key]}
                        )
                    else:
                        compare_dicts(new_path, base[key], curr[key])
            elif isinstance(base, list) and isinstance(curr, list):
                if base != curr:
                    change = f"Modified: {path} (list changed)"
                    changes.append(change)
                    drift_details["changes"].append(
                        {
                            "type": "modified",
                            "path": path,
                            "old_value": base,
                            "new_value": curr,
                        }
                    )
            else:
                if base != curr:
                    change = f"Modified: {path} ('{base}' -> '{curr}')"
                    changes.append(change)
                    drift_details["changes"].append(
                        {
                            "type": "modified",
                            "path": path,
                            "old_value": base,
                            "new_value": curr,
                        }
                    )

        compare_dicts("", baseline_config, current_filtered)

        has_drift = len(changes) > 0
        return has_drift, changes, drift_details

    def generate_drift_report(
        self, drift_details: Dict[str, Any], output_path: Optional[Path] = None
    ) -> str:
        """
        Generate human-readable drift report.

        Args:
            drift_details: Drift details from detect_drift().
            output_path: Optional path to save report.

        Returns:
            Report as string.
        """
        report_lines = [
            "=" * 80,
            "CONFIGURATION DRIFT REPORT",
            "=" * 80,
            f"Detected at: {drift_details.get('detected_at', 'unknown')}",
            f"Baseline version: {drift_details.get('baseline_version', 'unknown')}",
            f"Baseline timestamp: {drift_details.get('baseline_timestamp', 'unknown')}",
            f"Baseline checksum: {drift_details.get('baseline_checksum', 'unknown')}",
            f"Current checksum: {drift_details.get('current_checksum', 'unknown')}",
            "",
            f"Total changes detected: {len(drift_details.get('changes', []))}",
            "",
        ]

        changes = drift_details.get("changes", [])
        if changes:
            report_lines.append("CHANGES:")
            report_lines.append("-" * 80)

            for change in changes:
                change_type = change.get("type", "unknown").upper()
                path = change.get("path", "")

                if change_type == "ADDED":
                    report_lines.append(f"  [ADDED] {path}")
                    report_lines.append(f"    Value: {change.get('value', '')}")
                elif change_type == "REMOVED":
                    report_lines.append(f"  [REMOVED] {path}")
                    report_lines.append(f"    Old value: {change.get('old_value', '')}")
                elif change_type == "MODIFIED":
                    report_lines.append(f"  [MODIFIED] {path}")
                    report_lines.append(f"    Old: {change.get('old_value', '')}")
                    report_lines.append(f"    New: {change.get('new_value', '')}")

                report_lines.append("")
        else:
            report_lines.append("No changes detected.")

        report_lines.append("=" * 80)

        report = "\n".join(report_lines)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                f.write(report)
            logger.info("Drift report saved to: %s", output_path)

        return report

    def list_baselines(self, environment: Optional[str] = None) -> List[Dict[str, str]]:
        """
        List available baselines.

        Args:
            environment: Optional environment filter.

        Returns:
            List of baseline metadata.
        """
        pattern = f"{environment}_*_baseline.json" if environment else "*_baseline.json"
        baselines = []

        for filepath in sorted(self.baseline_dir.glob(pattern), reverse=True):
            try:
                with open(filepath, "r") as f:
                    baseline = json.load(f)
                baselines.append(
                    {
                        "filename": filepath.name,
                        "environment": baseline.get("environment", "unknown"),
                        "version": baseline.get("version", "unknown"),
                        "timestamp": baseline.get("timestamp", "unknown"),
                        "checksum": baseline.get("checksum", "unknown"),
                    }
                )
            except Exception as e:
                logger.warning("Failed to load baseline %s: %s", filepath, e)

        return baselines
