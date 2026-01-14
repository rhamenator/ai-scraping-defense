"""
Secret compliance monitoring and usage analytics.

This module provides functionality to monitor secret usage patterns, detect
compliance violations, and generate analytics reports.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from prometheus_client import Counter, Gauge, Histogram

from src.shared.audit import log_event
from src.shared.vault_client import VaultClient, get_vault_client

logger = logging.getLogger(__name__)


# Prometheus metrics for secret operations
secret_access_counter = Counter(
    "vault_secret_access_total",
    "Total number of secret access operations",
    ["path", "operation", "status"],
)

secret_rotation_counter = Counter(
    "vault_secret_rotation_total",
    "Total number of secret rotations",
    ["path", "status"],
)

secret_age_gauge = Gauge(
    "vault_secret_age_days",
    "Age of secret in days",
    ["path"],
)

secret_version_count_gauge = Gauge(
    "vault_secret_version_count",
    "Number of versions for a secret",
    ["path"],
)

secret_compliance_score_gauge = Gauge(
    "vault_secret_compliance_score",
    "Compliance score for a secret (0-100)",
    ["path"],
)

secret_operation_duration = Histogram(
    "vault_secret_operation_duration_seconds",
    "Duration of secret operations",
    ["operation"],
)


class ComplianceStatus(Enum):
    """Secret compliance status."""

    COMPLIANT = "compliant"
    WARNING = "warning"
    NON_COMPLIANT = "non_compliant"
    CRITICAL = "critical"


@dataclass
class ComplianceRule:
    """Rule for secret compliance checking."""

    name: str
    description: str
    severity: str  # "info", "warning", "critical"
    check_function: Any  # Callable that returns (bool, str)


@dataclass
class ComplianceCheck:
    """Result of a compliance check."""

    rule_name: str
    passed: bool
    severity: str
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SecretCompliancePolicy:
    """Policy defining compliance requirements for secrets."""

    path: str
    max_age_days: int = 90
    min_rotation_frequency_days: int = 90
    max_versions_to_keep: int = 10
    require_rotation_tracking: bool = True
    require_access_logging: bool = True
    allowed_access_patterns: Optional[List[str]] = None
    mount_point: str = "secret"


class SecretComplianceMonitor:
    """Monitor for secret compliance and usage analytics."""

    def __init__(self, vault_client: Optional[VaultClient] = None):
        """
        Initialize the compliance monitor.

        Args:
            vault_client: VaultClient instance. If None, uses global client.
        """
        self.vault_client = vault_client or get_vault_client()
        if not self.vault_client:
            raise ValueError("Vault client is required for compliance monitoring")

    def check_age_compliance(
        self, path: str, max_age_days: int, mount_point: str = "secret"
    ) -> ComplianceCheck:
        """
        Check if secret age complies with policy.

        Args:
            path: Path to the secret
            max_age_days: Maximum allowed age in days
            mount_point: KV mount point

        Returns:
            ComplianceCheck result
        """
        try:
            metadata = self.vault_client.read_secret_metadata(path, mount_point)
            if not metadata:
                return ComplianceCheck(
                    rule_name="age_compliance",
                    passed=False,
                    severity="critical",
                    message=f"Secret not found at {path}",
                )

            created_time = metadata.get("created_time")
            if not created_time:
                return ComplianceCheck(
                    rule_name="age_compliance",
                    passed=False,
                    severity="warning",
                    message="Cannot determine secret age",
                )

            created_dt = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
            age = datetime.utcnow() - created_dt.replace(tzinfo=None)
            age_days = age.days

            # Update metric
            secret_age_gauge.labels(path=path).set(age_days)

            if age_days > max_age_days:
                return ComplianceCheck(
                    rule_name="age_compliance",
                    passed=False,
                    severity="critical",
                    message=f"Secret age ({age_days} days) exceeds maximum ({max_age_days} days)",
                )

            return ComplianceCheck(
                rule_name="age_compliance",
                passed=True,
                severity="info",
                message=f"Secret age ({age_days} days) is within limits",
            )

        except Exception as e:
            logger.error(f"Error checking age compliance for {path}: {e}")
            return ComplianceCheck(
                rule_name="age_compliance",
                passed=False,
                severity="warning",
                message=f"Error checking compliance: {e}",
            )

    def check_version_compliance(
        self, path: str, max_versions: int, mount_point: str = "secret"
    ) -> ComplianceCheck:
        """
        Check if secret version count complies with policy.

        Args:
            path: Path to the secret
            max_versions: Maximum allowed versions
            mount_point: KV mount point

        Returns:
            ComplianceCheck result
        """
        try:
            metadata = self.vault_client.read_secret_metadata(path, mount_point)
            if not metadata:
                return ComplianceCheck(
                    rule_name="version_compliance",
                    passed=False,
                    severity="warning",
                    message=f"Secret not found at {path}",
                )

            versions = metadata.get("versions", {})
            version_count = len(versions)

            # Update metric
            secret_version_count_gauge.labels(path=path).set(version_count)

            if version_count > max_versions:
                return ComplianceCheck(
                    rule_name="version_compliance",
                    passed=False,
                    severity="warning",
                    message=f"Version count ({version_count}) exceeds maximum ({max_versions})",
                )

            return ComplianceCheck(
                rule_name="version_compliance",
                passed=True,
                severity="info",
                message=f"Version count ({version_count}) is within limits",
            )

        except Exception as e:
            logger.error(f"Error checking version compliance for {path}: {e}")
            return ComplianceCheck(
                rule_name="version_compliance",
                passed=False,
                severity="warning",
                message=f"Error checking compliance: {e}",
            )

    def check_rotation_tracking(
        self, path: str, mount_point: str = "secret"
    ) -> ComplianceCheck:
        """
        Check if secret has rotation tracking metadata.

        Args:
            path: Path to the secret
            mount_point: KV mount point

        Returns:
            ComplianceCheck result
        """
        try:
            secret_data = self.vault_client.read_secret(path, mount_point=mount_point)
            if not secret_data:
                return ComplianceCheck(
                    rule_name="rotation_tracking",
                    passed=False,
                    severity="warning",
                    message=f"Secret not found at {path}",
                )

            has_rotation_info = (
                "rotated_at" in secret_data or "rotation_policy" in secret_data
            )

            if not has_rotation_info:
                return ComplianceCheck(
                    rule_name="rotation_tracking",
                    passed=False,
                    severity="warning",
                    message="Secret lacks rotation tracking metadata",
                )

            return ComplianceCheck(
                rule_name="rotation_tracking",
                passed=True,
                severity="info",
                message="Secret has rotation tracking metadata",
            )

        except Exception as e:
            logger.error(f"Error checking rotation tracking for {path}: {e}")
            return ComplianceCheck(
                rule_name="rotation_tracking",
                passed=False,
                severity="warning",
                message=f"Error checking compliance: {e}",
            )

    def check_compliance(self, policy: SecretCompliancePolicy) -> Dict[str, Any]:
        """
        Check compliance for a secret against policy.

        Args:
            policy: Compliance policy

        Returns:
            Dictionary with compliance results
        """
        result = {
            "path": policy.path,
            "status": ComplianceStatus.COMPLIANT.value,
            "checks": [],
            "score": 100,
            "timestamp": datetime.utcnow().isoformat(),
        }

        checks = []

        # Check age compliance
        age_check = self.check_age_compliance(
            policy.path, policy.max_age_days, policy.mount_point
        )
        checks.append(age_check)

        # Check version compliance
        version_check = self.check_version_compliance(
            policy.path, policy.max_versions_to_keep, policy.mount_point
        )
        checks.append(version_check)

        # Check rotation tracking if required
        if policy.require_rotation_tracking:
            rotation_check = self.check_rotation_tracking(
                policy.path, policy.mount_point
            )
            checks.append(rotation_check)

        # Calculate compliance score and status
        total_checks = len(checks)
        passed_checks = sum(1 for check in checks if check.passed)
        critical_failures = sum(
            1 for check in checks if not check.passed and check.severity == "critical"
        )
        warning_failures = sum(
            1 for check in checks if not check.passed and check.severity == "warning"
        )

        result["checks"] = [
            {
                "rule": check.rule_name,
                "passed": check.passed,
                "severity": check.severity,
                "message": check.message,
                "timestamp": check.timestamp.isoformat(),
            }
            for check in checks
        ]

        # Calculate score (critical failures -30, warnings -10)
        score = 100 - (critical_failures * 30) - (warning_failures * 10)
        score = max(0, score)
        result["score"] = score

        # Update metric
        secret_compliance_score_gauge.labels(path=policy.path).set(score)

        # Determine overall status
        if critical_failures > 0:
            result["status"] = ComplianceStatus.CRITICAL.value
        elif warning_failures > 0:
            result["status"] = ComplianceStatus.WARNING.value
        else:
            result["status"] = ComplianceStatus.COMPLIANT.value

        # Log compliance check
        log_event(
            "secret_compliance_check",
            {
                "path": policy.path,
                "status": result["status"],
                "score": score,
                "checks_passed": passed_checks,
                "checks_total": total_checks,
            },
        )

        return result

    def audit_multiple_secrets(
        self, policies: List[SecretCompliancePolicy]
    ) -> List[Dict[str, Any]]:
        """
        Audit compliance for multiple secrets.

        Args:
            policies: List of compliance policies

        Returns:
            List of compliance results
        """
        results = []
        for policy in policies:
            result = self.check_compliance(policy)
            results.append(result)
        return results

    def generate_compliance_report(
        self, policies: List[SecretCompliancePolicy]
    ) -> Dict[str, Any]:
        """
        Generate comprehensive compliance report.

        Args:
            policies: List of compliance policies

        Returns:
            Dictionary with report data
        """
        results = self.audit_multiple_secrets(policies)

        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "total_secrets": len(results),
            "compliant": sum(
                1 for r in results if r["status"] == ComplianceStatus.COMPLIANT.value
            ),
            "warning": sum(
                1 for r in results if r["status"] == ComplianceStatus.WARNING.value
            ),
            "critical": sum(
                1 for r in results if r["status"] == ComplianceStatus.CRITICAL.value
            ),
            "average_score": (
                sum(r["score"] for r in results) / len(results) if results else 0
            ),
            "results": results,
        }

        # Log report generation
        log_event(
            "compliance_report_generated",
            {
                "total_secrets": report["total_secrets"],
                "compliant": report["compliant"],
                "warning": report["warning"],
                "critical": report["critical"],
                "average_score": report["average_score"],
            },
        )

        return report

    def track_secret_access(
        self, path: str, operation: str, status: str = "success"
    ) -> None:
        """
        Track secret access for analytics.

        Args:
            path: Path to the secret
            operation: Operation type (read, write, delete, etc.)
            status: Operation status (success, failure)
        """
        # Update Prometheus counter
        secret_access_counter.labels(
            path=path, operation=operation, status=status
        ).inc()

        # Log access event
        log_event(
            "secret_access",
            {
                "path": path,
                "operation": operation,
                "status": status,
            },
        )

    def track_secret_rotation(self, path: str, status: str = "success") -> None:
        """
        Track secret rotation for analytics.

        Args:
            path: Path to the secret
            status: Rotation status (success, failure)
        """
        # Update Prometheus counter
        secret_rotation_counter.labels(path=path, status=status).inc()

        # Log rotation event
        log_event(
            "secret_rotation",
            {
                "path": path,
                "status": status,
            },
        )


def create_default_compliance_policies() -> List[SecretCompliancePolicy]:
    """
    Create default compliance policies for common secrets.

    Returns:
        List of default compliance policies
    """
    return [
        SecretCompliancePolicy(
            path="database/postgres",
            max_age_days=90,
            min_rotation_frequency_days=90,
            max_versions_to_keep=10,
        ),
        SecretCompliancePolicy(
            path="database/redis",
            max_age_days=90,
            min_rotation_frequency_days=90,
            max_versions_to_keep=10,
        ),
        SecretCompliancePolicy(
            path="admin/credentials",
            max_age_days=90,
            min_rotation_frequency_days=90,
            max_versions_to_keep=15,
        ),
        SecretCompliancePolicy(
            path="system/seed",
            max_age_days=180,
            min_rotation_frequency_days=180,
            max_versions_to_keep=5,
        ),
        SecretCompliancePolicy(
            path="auth/jwt_secret",
            max_age_days=90,
            min_rotation_frequency_days=90,
            max_versions_to_keep=10,
        ),
    ]
