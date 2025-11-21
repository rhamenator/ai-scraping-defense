#!/usr/bin/env python3
"""
Security Metrics Collection and Reporting for DevSecOps Integration.

This script collects security metrics from various sources and generates
comprehensive reports for tracking security posture over time.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SecurityMetrics:
    """Collect and aggregate security metrics from multiple sources."""

    def __init__(self, reports_dir: Path):
        self.reports_dir = reports_dir
        self.metrics: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {},
            "tools": {},
            "trends": {},
        }

    def collect_semgrep_metrics(self) -> Dict[str, int]:
        """Collect metrics from Semgrep SAST results."""
        semgrep_file = self.reports_dir / "semgrep.json"
        if not semgrep_file.exists():
            return {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}

        try:
            with open(semgrep_file, "r") as f:
                data = json.load(f)

            results = data.get("results", [])
            metrics = {
                "total": len(results),
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
            }

            for result in results:
                severity = result.get("extra", {}).get("severity", "").lower()
                if severity == "critical":
                    metrics["critical"] += 1
                elif severity == "error":
                    metrics["high"] += 1
                elif severity == "warning":
                    metrics["medium"] += 1
                elif severity == "info":
                    metrics["low"] += 1

            return metrics
        except Exception as e:
            print(f"Error parsing Semgrep results: {e}", file=sys.stderr)
            return {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}

    def collect_bandit_metrics(self) -> Dict[str, int]:
        """Collect metrics from Bandit security scanner."""
        bandit_file = self.reports_dir / "bandit.json"
        if not bandit_file.exists():
            return {"total": 0, "high": 0, "medium": 0, "low": 0}

        try:
            with open(bandit_file, "r") as f:
                data = json.load(f)

            results = data.get("results", [])
            metrics = {"total": len(results), "high": 0, "medium": 0, "low": 0}

            for result in results:
                severity = result.get("issue_severity", "").lower()
                if severity == "high":
                    metrics["high"] += 1
                elif severity == "medium":
                    metrics["medium"] += 1
                elif severity == "low":
                    metrics["low"] += 1

            return metrics
        except Exception as e:
            print(f"Error parsing Bandit results: {e}", file=sys.stderr)
            return {"total": 0, "high": 0, "medium": 0, "low": 0}

    def collect_gitleaks_metrics(self) -> Dict[str, int]:
        """Collect metrics from Gitleaks secret scanner."""
        gitleaks_file = self.reports_dir / "gitleaks.json"
        if not gitleaks_file.exists():
            return {"total": 0, "secrets_found": 0}

        try:
            with open(gitleaks_file, "r") as f:
                data = json.load(f)

            secrets_count = len(data) if isinstance(data, list) else 0
            return {"total": secrets_count, "secrets_found": secrets_count}
        except Exception as e:
            print(f"Error parsing Gitleaks results: {e}", file=sys.stderr)
            return {"total": 0, "secrets_found": 0}

    def collect_trivy_metrics(self) -> Dict[str, int]:
        """Collect metrics from Trivy container scanner."""
        trivy_file = self.reports_dir / "trivy.json"
        if not trivy_file.exists():
            return {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}

        try:
            with open(trivy_file, "r") as f:
                data = json.load(f)

            metrics = {
                "total": 0,
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
            }

            results = data.get("Results", [])
            for result in results:
                vulns = result.get("Vulnerabilities", [])
                for vuln in vulns:
                    severity = vuln.get("Severity", "").upper()
                    metrics["total"] += 1
                    if severity == "CRITICAL":
                        metrics["critical"] += 1
                    elif severity == "HIGH":
                        metrics["high"] += 1
                    elif severity == "MEDIUM":
                        metrics["medium"] += 1
                    elif severity == "LOW":
                        metrics["low"] += 1

            return metrics
        except Exception as e:
            print(f"Error parsing Trivy results: {e}", file=sys.stderr)
            return {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}

    def collect_dependency_metrics(self) -> Dict[str, int]:
        """Collect metrics from dependency scanners."""
        pip_audit_file = self.reports_dir / "pip-audit.json"
        metrics = {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}

        if not pip_audit_file.exists():
            return metrics

        try:
            with open(pip_audit_file, "r") as f:
                data = json.load(f)

            vulns = data.get("vulnerabilities", [])
            metrics["total"] = len(vulns)

            # Count by severity (simplified parsing)
            for vuln in vulns:
                vuln_str = str(vuln).upper()
                if "CRITICAL" in vuln_str:
                    metrics["critical"] += 1
                elif "HIGH" in vuln_str:
                    metrics["high"] += 1
                elif "MEDIUM" in vuln_str:
                    metrics["medium"] += 1
                else:
                    metrics["low"] += 1

            return metrics
        except Exception as e:
            print(f"Error parsing dependency scan results: {e}", file=sys.stderr)
            return metrics

    def aggregate_metrics(self) -> None:
        """Aggregate all collected metrics."""
        self.metrics["tools"]["semgrep"] = self.collect_semgrep_metrics()
        self.metrics["tools"]["bandit"] = self.collect_bandit_metrics()
        self.metrics["tools"]["gitleaks"] = self.collect_gitleaks_metrics()
        self.metrics["tools"]["trivy"] = self.collect_trivy_metrics()
        self.metrics["tools"]["dependencies"] = self.collect_dependency_metrics()

        # Calculate summary
        summary = {
            "total_issues": 0,
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "secrets": 0,
        }

        for tool, tool_metrics in self.metrics["tools"].items():
            summary["total_issues"] += tool_metrics.get("total", 0)
            summary["critical"] += tool_metrics.get("critical", 0)
            summary["high"] += tool_metrics.get("high", 0)
            summary["medium"] += tool_metrics.get("medium", 0)
            summary["low"] += tool_metrics.get("low", 0)
            summary["secrets"] += tool_metrics.get("secrets_found", 0)

        self.metrics["summary"] = summary

    def calculate_security_score(self) -> float:
        """
        Calculate a security score (0-100) based on findings.
        Higher score = better security posture.
        """
        summary = self.metrics["summary"]

        # Weight different severities
        deductions = (
            summary["critical"] * 10
            + summary["high"] * 5
            + summary["medium"] * 2
            + summary["low"] * 0.5
            + summary["secrets"] * 20
        )

        # Start at 100 and deduct points
        score = max(0, 100 - deductions)

        self.metrics["security_score"] = round(score, 2)
        return score

    def generate_report(self, output_file: Path | None = None) -> None:
        """Generate a comprehensive security metrics report."""
        self.aggregate_metrics()
        self.calculate_security_score()

        if output_file:
            with open(output_file, "w") as f:
                json.dump(self.metrics, f, indent=2)
            print(f"Security metrics report generated: {output_file}")
        else:
            print(json.dumps(self.metrics, indent=2))

    def print_summary(self) -> None:
        """Print a human-readable summary of security metrics."""
        summary = self.metrics["summary"]
        score = self.metrics.get("security_score", 0)

        print("\n" + "=" * 60)
        print("SECURITY METRICS SUMMARY")
        print("=" * 60)
        print(f"Timestamp: {self.metrics['timestamp']}")
        print(f"\nSecurity Score: {score}/100")
        print(f"\nFindings:")
        print(f"  🔴 Critical:  {summary['critical']}")
        print(f"  🟠 High:      {summary['high']}")
        print(f"  🟡 Medium:    {summary['medium']}")
        print(f"  🟢 Low:       {summary['low']}")
        print(f"  🔑 Secrets:   {summary['secrets']}")
        print(f"\nTotal Issues: {summary['total_issues']}")
        print("\nTool Breakdown:")
        for tool, metrics in self.metrics["tools"].items():
            total = metrics.get("total", 0)
            print(f"  - {tool.capitalize()}: {total} findings")
        print("=" * 60 + "\n")


def main():
    """Main entry point for security metrics collection."""
    parser = argparse.ArgumentParser(
        description="Collect and report security metrics for DevSecOps"
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=PROJECT_ROOT / "reports" / "security-gate",
        help="Directory containing security scan reports",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file for metrics JSON (default: stdout)",
    )
    parser.add_argument(
        "--summary",
        "-s",
        action="store_true",
        help="Print human-readable summary",
    )

    args = parser.parse_args()

    if not args.reports_dir.exists():
        print(
            f"Reports directory not found: {args.reports_dir}", file=sys.stderr
        )
        sys.exit(1)

    collector = SecurityMetrics(args.reports_dir)
    collector.generate_report(args.output)

    if args.summary:
        collector.print_summary()


if __name__ == "__main__":
    main()
