#!/usr/bin/env python3
"""Comprehensive configuration validation CLI tool."""

import argparse
import logging
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.shared.config_drift import ConfigDrift  # noqa: E402
from src.shared.config_validator import (  # noqa: E402
    ConfigLoader,
    ConfigValidationError,
)
from src.shared.feature_flags import FeatureFlagManager  # noqa: E402

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def validate_configuration(
    env_file: Path, strict: bool = True, environment: str = "production"
) -> bool:
    """
    Validate configuration from environment file.

    Args:
        env_file: Path to .env file
        strict: If True, fail on validation errors
        environment: Deployment environment

    Returns:
        True if validation passes, False otherwise
    """
    logger.info("Validating configuration from: %s", env_file)
    logger.info("Environment: %s", environment)

    # Load environment variables from file
    env_vars = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars[key] = value
    else:
        logger.error("Environment file not found: %s", env_file)
        return False

    # Load and validate configuration
    try:
        loader = ConfigLoader(strict=strict)
        config = loader.load_from_env(env_vars)

        logger.info("✓ Configuration loaded successfully")
        logger.info("  - Model URI: %s", config.model_uri)
        logger.info("  - Environment: %s", config.app_env.value)
        logger.info("  - Tenant ID: %s", config.tenant_id)
        logger.info("  - Log Level: %s", config.log_level.value)

        # Perform additional validation
        is_valid, errors = loader.validate_config(config)

        if errors:
            logger.error(
                "✗ Configuration validation failed with %d error(s):", len(errors)
            )
            for error in errors:
                logger.error("  - %s", error)
            return False
        else:
            logger.info("✓ Configuration validation passed")
            return True

    except ConfigValidationError as e:
        logger.error("✗ Configuration validation error: %s", e)
        return False
    except Exception as e:
        logger.error("✗ Unexpected error during validation: %s", e)
        if strict:
            raise
        return False


def validate_feature_flags(environment: str = "production") -> bool:
    """
    Validate feature flag configuration.

    Args:
        environment: Deployment environment

    Returns:
        True if validation passes, False otherwise
    """
    logger.info("Validating feature flags for environment: %s", environment)

    try:
        manager = FeatureFlagManager(environment=environment)
        features = manager.get_all_features()

        logger.info("✓ Feature flags loaded successfully")
        logger.info("  - Total features: %d", len(features))
        enabled = manager.get_enabled_features()
        logger.info("  - Enabled features: %d", len(enabled))

        # List enabled features
        if enabled:
            logger.info("  Enabled features:")
            for feature_name in sorted(enabled):
                feature = manager.get_feature(feature_name)
                logger.info("    - %s: %s", feature_name, feature.description)

        return True

    except Exception as e:
        logger.error("✗ Feature flag validation failed: %s", e)
        return False


def check_drift(
    env_file: Path,
    environment: str = "production",
    baseline_version: str = None,
    save_baseline: bool = False,
) -> bool:
    """
    Check for configuration drift.

    Args:
        env_file: Path to .env file
        environment: Deployment environment
        baseline_version: Optional baseline version to compare against
        save_baseline: If True, save current config as baseline

    Returns:
        True if no drift detected or baseline saved, False otherwise
    """
    logger.info("Checking configuration drift...")

    # Load current configuration
    env_vars = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars[key] = value

    try:
        loader = ConfigLoader(strict=False)
        config = loader.load_from_env(env_vars)
        config_dict = config.to_dict()

        drift_detector = ConfigDrift()

        if save_baseline:
            # Save current config as baseline
            baseline_path = drift_detector.save_baseline(
                config_dict, environment, version=baseline_version
            )
            logger.info("✓ Baseline saved: %s", baseline_path)
            return True

        # Detect drift
        has_drift, changes, drift_details = drift_detector.detect_drift(
            config_dict, environment=environment
        )

        if has_drift:
            logger.warning("⚠ Configuration drift detected!")
            logger.warning("  - Changes: %d", len(changes))

            # Generate and display report
            report = drift_detector.generate_drift_report(drift_details)
            print("\n" + report)
            return False
        else:
            logger.info("✓ No configuration drift detected")
            return True

    except Exception as e:
        logger.error("✗ Drift detection failed: %s", e)
        return False


def list_baselines(environment: str = None) -> bool:
    """
    List available configuration baselines.

    Args:
        environment: Optional environment filter

    Returns:
        Always returns True
    """
    try:
        drift_detector = ConfigDrift()
        baselines = drift_detector.list_baselines(environment)

        if not baselines:
            logger.info("No baselines found")
            return True

        logger.info("Available baselines:")
        logger.info("-" * 80)
        for baseline in baselines:
            logger.info("  Environment: %s", baseline["environment"])
            logger.info("  Version: %s", baseline["version"])
            logger.info("  Timestamp: %s", baseline["timestamp"])
            logger.info("  Checksum: %s", baseline["checksum"])
            logger.info("  File: %s", baseline["filename"])
            logger.info("-" * 80)

        return True

    except Exception as e:
        logger.error("✗ Failed to list baselines: %s", e)
        return False


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Comprehensive configuration validation tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate configuration
  %(prog)s validate --env-file .env --environment production

  # Validate feature flags
  %(prog)s features --environment staging

  # Check for configuration drift
  %(prog)s drift --env-file .env --environment production

  # Save configuration baseline
  %(prog)s drift --env-file .env --save-baseline --environment production

  # List available baselines
  %(prog)s list-baselines --environment production
        """,
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate", help="Validate configuration from .env file"
    )
    validate_parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to .env file (default: .env)",
    )
    validate_parser.add_argument(
        "--environment",
        choices=["development", "staging", "production", "testing"],
        default="production",
        help="Deployment environment (default: production)",
    )
    validate_parser.add_argument(
        "--strict",
        action="store_true",
        default=True,
        help="Fail on validation errors (default: True)",
    )

    # Feature flags command
    features_parser = subparsers.add_parser(
        "features", help="Validate feature flag configuration"
    )
    features_parser.add_argument(
        "--environment",
        choices=["development", "staging", "production", "testing"],
        default="production",
        help="Deployment environment (default: production)",
    )

    # Drift detection command
    drift_parser = subparsers.add_parser("drift", help="Check for configuration drift")
    drift_parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to .env file (default: .env)",
    )
    drift_parser.add_argument(
        "--environment",
        choices=["development", "staging", "production", "testing"],
        default="production",
        help="Deployment environment (default: production)",
    )
    drift_parser.add_argument(
        "--baseline-version", help="Baseline version to compare against"
    )
    drift_parser.add_argument(
        "--save-baseline",
        action="store_true",
        help="Save current configuration as baseline",
    )

    # List baselines command
    list_parser = subparsers.add_parser(
        "list-baselines", help="List available configuration baselines"
    )
    list_parser.add_argument(
        "--environment",
        choices=["development", "staging", "production", "testing"],
        help="Filter by environment",
    )

    args = parser.parse_args()

    setup_logging(args.verbose)

    if not args.command:
        parser.print_help()
        return 1

    success = False

    if args.command == "validate":
        success = validate_configuration(args.env_file, args.strict, args.environment)

    elif args.command == "features":
        success = validate_feature_flags(args.environment)

    elif args.command == "drift":
        success = check_drift(
            args.env_file,
            args.environment,
            args.baseline_version,
            args.save_baseline,
        )

    elif args.command == "list-baselines":
        success = list_baselines(args.environment)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
