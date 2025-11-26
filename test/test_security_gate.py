"""Tests for DevSecOps security gate implementation."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_security_policy_exists():
    """Verify security policy configuration exists."""
    policy_path = PROJECT_ROOT / ".github" / "security-policy.yml"
    assert policy_path.exists(), "Security policy file must exist"


def test_security_gate_workflow_exists():
    """Verify security gate workflow exists."""
    workflow_path = PROJECT_ROOT / ".github" / "workflows" / "security-gate.yml"
    assert workflow_path.exists(), "Security gate workflow must exist"


def test_pre_commit_has_security_hooks():
    """Verify pre-commit configuration includes security hooks."""
    pre_commit_path = PROJECT_ROOT / ".pre-commit-config.yaml"
    assert pre_commit_path.exists(), "Pre-commit config must exist"

    with open(pre_commit_path, "r") as f:
        content = f.read()

    # Verify security-related hooks are present
    assert "gitleaks" in content, "Gitleaks hook must be configured"
    assert "bandit" in content, "Bandit hook must be configured"
    assert "safety" in content or "python-safety" in content, (
        "Safety/pip-audit hook must be configured"
    )


def test_bandit_configuration_exists():
    """Verify Bandit configuration exists in pyproject.toml."""
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml must exist"

    with open(pyproject_path, "r") as f:
        content = f.read()

    assert "[tool.bandit]" in content, "Bandit configuration must exist"


def test_security_metrics_script_exists():
    """Verify security metrics collection script exists."""
    metrics_script = (
        PROJECT_ROOT / "scripts" / "security" / "security_metrics.py"
    )
    assert metrics_script.exists(), "Security metrics script must exist"
    assert metrics_script.stat().st_mode & 0o111, (
        "Security metrics script must be executable"
    )


def test_security_metrics_script_runs():
    """Verify security metrics script runs without errors."""
    metrics_script = (
        PROJECT_ROOT / "scripts" / "security" / "security_metrics.py"
    )

    # Create a temporary reports directory with mock data
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        reports_dir = Path(tmpdir)

        # Create mock report files
        (reports_dir / "semgrep.json").write_text(
            json.dumps({"results": []})
        )
        (reports_dir / "bandit.json").write_text(json.dumps({"results": []}))
        (reports_dir / "gitleaks.json").write_text(json.dumps([]))
        (reports_dir / "trivy.json").write_text(json.dumps({"Results": []}))
        (reports_dir / "pip-audit.json").write_text(
            json.dumps({"vulnerabilities": []})
        )

        # Run the script
        result = subprocess.run(
            [
                sys.executable,
                str(metrics_script),
                "--reports-dir",
                str(reports_dir),
                "--summary",
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"Security metrics script failed: {result.stderr}"
        )
        assert "Security Score:" in result.stdout, (
            "Security score should be in output"
        )


def test_security_gate_threshold_configuration():
    """Verify security gate has proper threshold configuration."""
    policy_path = PROJECT_ROOT / ".github" / "security-policy.yml"

    with open(policy_path, "r") as f:
        content = f.read()

    # Verify key configurations
    assert "security_gate:" in content
    assert "severity_threshold:" in content
    assert "thresholds:" in content
    assert "critical:" in content
    assert "high:" in content


def test_shift_left_practices_documented():
    """Verify shift-left security practices are documented."""
    policy_path = PROJECT_ROOT / ".github" / "security-policy.yml"

    with open(policy_path, "r") as f:
        content = f.read()

    assert "shift_left:" in content, "Shift-left section must be documented"
    assert "pre_commit:" in content, "Pre-commit practices must be documented"


@pytest.mark.security
def test_no_hardcoded_secrets_in_config():
    """Verify no hardcoded secrets in configuration files."""
    # Check security policy
    policy_path = PROJECT_ROOT / ".github" / "security-policy.yml"

    with open(policy_path, "r") as f:
        content = f.read()

    # Look for common secret patterns
    sensitive_patterns = [
        "password",
        "api_key",
        "secret_key",
        "access_token",
    ]

    for pattern in sensitive_patterns:
        # Ensure no actual values after the pattern
        lines = content.split("\n")
        for line in lines:
            if pattern in line.lower() and ":" in line:
                # Extract value after colon
                value = line.split(":", 1)[1].strip()
                # Value should be empty or a placeholder
                assert value in ["", '""', "''"], (
                    f"No hardcoded values for {pattern}"
                )


@pytest.mark.security
def test_security_controls_workflow_integration():
    """Verify security-controls workflow has proper DevSecOps integration."""
    workflow_path = (
        PROJECT_ROOT / ".github" / "workflows" / "security-controls.yml"
    )
    assert workflow_path.exists()

    with open(workflow_path, "r") as f:
        content = f.read()

    # Verify security tools are integrated
    assert "bandit" in content.lower()
    assert "trivy" in content.lower()


def test_comprehensive_security_audit_workflow_exists():
    """Verify comprehensive security audit workflow exists."""
    workflow_path = (
        PROJECT_ROOT
        / ".github"
        / "workflows"
        / "comprehensive-security-audit.yml"
    )
    assert workflow_path.exists()


def test_security_gate_integrates_with_ci():
    """Verify security gate can integrate with CI pipeline."""
    ci_workflow = PROJECT_ROOT / ".github" / "workflows" / "ci-tests.yml"
    assert ci_workflow.exists()

    with open(ci_workflow, "r") as f:
        content = f.read()

    # Verify CI has proper permissions for security
    assert "security-events: write" in content or "security-events:" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
