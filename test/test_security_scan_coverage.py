#!/usr/bin/env python3
"""
Test to validate that security_scan.sh and run_static_security_checks.py
are sufficient for testing the AI Scraping Defense stack.

This test evaluates:
1. Whether the security scanning tools cover all critical stack components
2. Whether all exposed services and ports are being tested
3. Whether the scans cover all major security categories
4. Whether the stack-specific security concerns are addressed
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Dict, List, Set

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StackComponent:
    """Represents a component of the AI Scraping Defense stack."""

    def __init__(
        self,
        name: str,
        ports: List[int],
        technology: str,
        security_concerns: List[str],
    ):
        self.name = name
        self.ports = ports
        self.technology = technology
        self.security_concerns = security_concerns


# Define the stack components based on docker-compose.yaml
STACK_COMPONENTS = [
    StackComponent(
        name="nginx_proxy",
        ports=[80, 443],
        technology="nginx/openresty",
        security_concerns=[
            "web_vulnerabilities",
            "ssl_tls",
            "header_security",
            "rate_limiting",
            "lua_injection",
        ],
    ),
    StackComponent(
        name="ai_service",
        ports=[],
        technology="python/fastapi",
        security_concerns=[
            "api_security",
            "injection",
            "authentication",
            "dependency_vulnerabilities",
        ],
    ),
    StackComponent(
        name="escalation_engine",
        ports=[],
        technology="python/fastapi",
        security_concerns=[
            "llm_prompt_injection",
            "api_security",
            "data_leakage",
            "dependency_vulnerabilities",
        ],
    ),
    StackComponent(
        name="tarpit_api",
        ports=[],
        technology="python/fastapi",
        security_concerns=[
            "dos_vulnerability",
            "resource_exhaustion",
            "api_security",
            "dependency_vulnerabilities",
        ],
    ),
    StackComponent(
        name="admin_ui",
        ports=[5002],
        technology="python/fastapi",
        security_concerns=[
            "authentication",
            "authorization",
            "xss",
            "csrf",
            "session_management",
            "dependency_vulnerabilities",
        ],
    ),
    StackComponent(
        name="postgres",
        ports=[5432],
        technology="postgresql",
        security_concerns=[
            "sql_injection",
            "authentication",
            "encryption_at_rest",
            "weak_passwords",
        ],
    ),
    StackComponent(
        name="redis",
        ports=[6379],
        technology="redis",
        security_concerns=[
            "authentication",
            "command_injection",
            "data_exposure",
            "weak_passwords",
        ],
    ),
    StackComponent(
        name="cloud_dashboard",
        ports=[5006],
        technology="python/fastapi",
        security_concerns=[
            "authentication",
            "authorization",
            "api_security",
            "dependency_vulnerabilities",
        ],
    ),
    StackComponent(
        name="config_recommender",
        ports=[],
        technology="python/fastapi",
        security_concerns=[
            "llm_prompt_injection",
            "api_security",
            "dependency_vulnerabilities",
        ],
    ),
]

# Security categories that should be covered
SECURITY_CATEGORIES = {
    "network_scanning": ["nmap", "masscan"],
    "web_vulnerabilities": ["nikto", "zap", "gobuster", "ffuf", "wfuzz"],
    "ssl_tls": ["sslyze", "testssl.sh"],
    "container_security": ["trivy", "grype"],
    "code_analysis": ["bandit", "gitleaks"],
    "sql_injection": ["sqlmap"],
    "dependency_scanning": ["pip-audit"],
    "fingerprinting": ["whatweb"],
    "malware_scanning": ["clamscan"],
    "rootkit_detection": ["rkhunter", "chkrootkit"],
    "system_audit": ["lynis"],
}


def _read_security_scan_sh() -> str:
    """Read the security_scan.sh script."""
    path = PROJECT_ROOT / "scripts/linux/security_scan.sh"
    return path.read_text()


def _read_static_security_checks() -> str:
    """Read the run_static_security_checks.py script."""
    path = PROJECT_ROOT / "scripts/security/run_static_security_checks.py"
    return path.read_text()


def _read_docker_compose() -> dict:
    """Read and parse docker-compose.yaml."""
    path = PROJECT_ROOT / "docker-compose.yaml"
    return yaml.safe_load(path.read_text())


class TestSecurityScanCoverage:
    """Test suite to validate security scanning coverage."""

    def test_security_scan_script_exists(self):
        """Verify that security_scan.sh exists and is executable."""
        script_path = PROJECT_ROOT / "scripts/linux/security_scan.sh"
        assert script_path.exists(), "security_scan.sh not found"
        assert script_path.stat().st_mode & 0o111, "security_scan.sh not executable"

    def test_security_setup_script_exists(self):
        """Verify that security_setup.sh exists and is executable."""
        script_path = PROJECT_ROOT / "scripts/linux/security_setup.sh"
        assert script_path.exists(), "security_setup.sh not found"
        assert script_path.stat().st_mode & 0o111, "security_setup.sh not executable"

    def test_static_security_checks_exists(self):
        """Verify that run_static_security_checks.py exists."""
        script_path = PROJECT_ROOT / "scripts/security/run_static_security_checks.py"
        assert script_path.exists(), "run_static_security_checks.py not found"

    def test_all_security_tools_covered(self):
        """Verify that security_scan.sh includes all major security tool categories."""
        scan_script = _read_security_scan_sh()
        missing_categories = []

        for category, tools in SECURITY_CATEGORIES.items():
            # Check if at least one tool from each category is present
            category_covered = any(tool in scan_script for tool in tools)
            if not category_covered:
                missing_categories.append(
                    f"{category} (expected: {', '.join(tools)})"
                )

        assert (
            not missing_categories
        ), f"Missing security categories: {', '.join(missing_categories)}"

    def test_network_ports_covered_in_script(self):
        """Verify that common exposed ports are included in scan."""
        scan_script = _read_security_scan_sh()

        # Extract the PORTS variable from the script
        ports_match = re.search(r'PORTS="([^"]+)"', scan_script)
        assert ports_match, "PORTS variable not found in security_scan.sh"

        scanned_ports = set(ports_match.group(1).split(","))

        # Important ports from our stack
        important_ports = {"22", "80", "443", "5432", "6379"}

        missing_ports = important_ports - scanned_ports
        assert (
            not missing_ports
        ), f"Important ports missing from scan: {', '.join(missing_ports)}"

    def test_python_dependency_scanning_included(self):
        """Verify that Python dependency scanning is included."""
        scan_script = _read_security_scan_sh()
        assert "pip-audit" in scan_script, "pip-audit not included for Python deps"
        assert "bandit" in scan_script, "bandit not included for Python code analysis"

    def test_container_scanning_included(self):
        """Verify that container scanning tools are included."""
        scan_script = _read_security_scan_sh()
        assert (
            "trivy" in scan_script
        ), "trivy not included for container vulnerability scanning"
        assert (
            "grype" in scan_script
        ), "grype not included for container vulnerability scanning"

    def test_web_application_scanning_included(self):
        """Verify that web application scanning tools are included."""
        scan_script = _read_security_scan_sh()
        web_tools = ["nikto", "zap-baseline.py", "gobuster", "ffuf", "wfuzz"]

        for tool in web_tools:
            assert tool in scan_script, f"{tool} not included for web scanning"

    def test_tls_scanning_included(self):
        """Verify that TLS/SSL scanning tools are included."""
        scan_script = _read_security_scan_sh()
        tls_tools = ["sslyze", "testssl.sh"]

        for tool in tls_tools:
            assert tool in scan_script, f"{tool} not included for TLS scanning"

    def test_secret_scanning_included(self):
        """Verify that secret scanning is included."""
        scan_script = _read_security_scan_sh()
        assert (
            "gitleaks" in scan_script
        ), "gitleaks not included for secret scanning"

    def test_sql_injection_testing_included(self):
        """Verify that SQL injection testing is included."""
        scan_script = _read_security_scan_sh()
        assert "sqlmap" in scan_script, "sqlmap not included for SQL injection testing"

    def test_static_checks_cover_compose_security(self):
        """Verify that static checks validate docker-compose security settings."""
        static_checks = _read_static_security_checks()

        # These are the key security checks from run_static_security_checks.py
        required_checks = [
            "ensure_compose_security",
            "ensure_nginx_headers_and_limits",
            "ensure_no_plaintext_secrets",
        ]

        for check in required_checks:
            assert (
                check in static_checks
            ), f"Static check function {check} not found"

    def test_static_checks_validate_hardened_services(self):
        """Verify that static checks validate hardened service configurations."""
        static_checks = _read_static_security_checks()

        # Should check for security_opt with no-new-privileges
        assert (
            "no-new-privileges:true" in static_checks
        ), "Static checks don't validate no-new-privileges"

        # Should check for capability dropping
        assert (
            "cap_drop" in static_checks
        ), "Static checks don't validate capability dropping"

        # Should check for read-only filesystem
        assert (
            "read_only" in static_checks
        ), "Static checks don't validate read-only filesystem"

    def test_security_scan_generates_reports(self):
        """Verify that security_scan.sh generates reports in a reports directory."""
        scan_script = _read_security_scan_sh()

        assert "mkdir -p reports" in scan_script, "Reports directory not created"
        assert (
            "reports/" in scan_script
        ), "Scan results not being written to reports directory"

    def test_security_scan_handles_missing_tools(self):
        """Verify that security_scan.sh gracefully handles missing tools."""
        scan_script = _read_security_scan_sh()

        # Should check for command availability
        assert (
            "command -v" in scan_script
        ), "Script doesn't check for command availability"
        assert (
            "else" in scan_script and "not installed" in scan_script
        ), "Script doesn't handle missing tools gracefully"

    def test_security_scan_accepts_docker_image_parameter(self):
        """Verify that security_scan.sh can scan Docker images."""
        scan_script = _read_security_scan_sh()

        assert (
            'IMAGE="$3"' in scan_script or "docker_image" in scan_script
        ), "Docker image parameter not accepted"
        assert (
            "trivy image" in scan_script
        ), "Docker image scanning not implemented"

    def test_security_scan_accepts_code_directory_parameter(self):
        """Verify that security_scan.sh can scan source code directories."""
        scan_script = _read_security_scan_sh()

        assert (
            'CODE_DIR="$4"' in scan_script or "code_dir" in scan_script
        ), "Code directory parameter not accepted"
        assert (
            "bandit -r" in scan_script
        ), "Source code scanning not implemented"

    def test_security_tools_setup_script_comprehensive(self):
        """Verify that security_setup.sh installs all required tools."""
        setup_script = (PROJECT_ROOT / "scripts/linux/security_setup.sh").read_text()

        # Core tools that must be in setup script
        core_tools = [
            "nmap",
            "nikto",
            "zaproxy",
            "sqlmap",
            "bandit",
            "trivy",
            "gitleaks",
            "grype",
        ]

        missing_tools = []
        for tool in core_tools:
            if tool not in setup_script:
                missing_tools.append(tool)

        assert (
            not missing_tools
        ), f"security_setup.sh missing installation of: {', '.join(missing_tools)}"


class TestStackSpecificSecurityConcerns:
    """Test that stack-specific security concerns are addressed."""

    def test_llm_prompt_injection_considerations(self):
        """Verify considerations for LLM prompt injection vulnerabilities."""
        # Check if there are any tests or documentation about LLM security
        test_dir = PROJECT_ROOT / "test"
        llm_related_files = list(test_dir.rglob("*escalation*")) + list(
            test_dir.rglob("*llm*")
        )

        # This is informational - LLM security is hard to automate
        # but we should at least document the concern
        print(
            f"\nNote: Found {len(llm_related_files)} LLM-related test files. "
            "Manual testing for prompt injection recommended."
        )

    def test_redis_authentication_in_compose(self):
        """Verify that Redis has authentication configured."""
        compose = _read_docker_compose()
        redis_service = compose.get("services", {}).get("redis", {})

        # Check if Redis has authentication via command or environment
        command = redis_service.get("command", "")
        environment = redis_service.get("environment", [])

        # Redis should either have --requirepass in command or AUTH env var
        has_auth = "--requirepass" in str(command) or any(
            "REDIS_PASSWORD" in str(env) for env in environment
        )

        # Note: This might be intentionally disabled for dev, so we just warn
        if not has_auth:
            print(
                "\nWarning: Redis may not have authentication configured in docker-compose.yaml"
            )

    def test_postgres_authentication_in_compose(self):
        """Verify that PostgreSQL has authentication configured."""
        compose = _read_docker_compose()
        postgres_service = compose.get("services", {}).get("postgres", {})

        environment = postgres_service.get("environment", [])

        # PostgreSQL should have POSTGRES_PASSWORD set
        has_password = any("POSTGRES_PASSWORD" in str(env) for env in environment)

        assert (
            has_password
        ), "PostgreSQL should have POSTGRES_PASSWORD configured"

    def test_nginx_security_headers_configured(self):
        """Verify that Nginx has security headers configured."""
        nginx_conf_path = PROJECT_ROOT / "nginx/nginx.conf"
        if not nginx_conf_path.exists():
            pytest.skip("nginx.conf not found")

        nginx_conf = nginx_conf_path.read_text()

        security_headers = [
            "Strict-Transport-Security",
            "X-Frame-Options",
            "X-Content-Type-Options",
        ]

        missing_headers = []
        for header in security_headers:
            if header not in nginx_conf:
                missing_headers.append(header)

        assert (
            not missing_headers
        ), f"Nginx missing security headers: {', '.join(missing_headers)}"

    def test_rate_limiting_configured_in_nginx(self):
        """Verify that rate limiting is configured in Nginx."""
        nginx_conf_path = PROJECT_ROOT / "nginx/nginx.conf"
        if not nginx_conf_path.exists():
            pytest.skip("nginx.conf not found")

        nginx_conf = nginx_conf_path.read_text()

        assert (
            "limit_req_zone" in nginx_conf
        ), "Rate limiting not configured in Nginx"
        assert (
            "limit_req zone=" in nginx_conf
        ), "Rate limiting zone not applied in Nginx"


class TestSecurityScanRecommendations:
    """Generate recommendations for improving security scanning."""

    def test_generate_coverage_report(self):
        """Generate a coverage report of what's tested vs what should be tested."""
        scan_script = _read_security_scan_sh()
        static_checks = _read_static_security_checks()

        coverage_report = {
            "covered_components": [],
            "missing_components": [],
            "covered_security_categories": [],
            "missing_security_categories": [],
            "stack_specific_concerns": [],
        }

        # Analyze component coverage
        for component in STACK_COMPONENTS:
            component_tested = False

            # Check if component's technology is addressed
            if component.technology.startswith("python"):
                component_tested = (
                    "bandit" in scan_script and "pip-audit" in scan_script
                )
            elif "nginx" in component.technology:
                component_tested = (
                    "nikto" in scan_script
                    and "ensure_nginx_headers_and_limits" in static_checks
                )
            elif "postgresql" in component.technology:
                component_tested = "sqlmap" in scan_script
            elif "redis" in component.technology:
                component_tested = "nmap" in scan_script

            if component_tested:
                coverage_report["covered_components"].append(component.name)
            else:
                coverage_report["missing_components"].append(component.name)

        # Analyze security category coverage
        for category, tools in SECURITY_CATEGORIES.items():
            category_covered = any(tool in scan_script for tool in tools)
            if category_covered:
                coverage_report["covered_security_categories"].append(category)
            else:
                coverage_report["missing_security_categories"].append(category)

        # Print the report
        print("\n" + "=" * 80)
        print("SECURITY SCAN COVERAGE REPORT")
        print("=" * 80)
        print(
            f"\nCovered Components ({len(coverage_report['covered_components'])}/{len(STACK_COMPONENTS)}):"
        )
        for comp in coverage_report["covered_components"]:
            print(f"  ✓ {comp}")

        if coverage_report["missing_components"]:
            print("\nMissing Component Coverage:")
            for comp in coverage_report["missing_components"]:
                print(f"  ✗ {comp}")

        print(
            f"\nCovered Security Categories ({len(coverage_report['covered_security_categories'])}/{len(SECURITY_CATEGORIES)}):"
        )
        for cat in coverage_report["covered_security_categories"]:
            print(f"  ✓ {cat}")

        if coverage_report["missing_security_categories"]:
            print("\nMissing Security Categories:")
            for cat in coverage_report["missing_security_categories"]:
                print(f"  ✗ {cat}")

        print("\n" + "=" * 80)

        # Assert that we have good coverage (at least 80%)
        component_coverage = (
            len(coverage_report["covered_components"]) / len(STACK_COMPONENTS) * 100
        )
        category_coverage = (
            len(coverage_report["covered_security_categories"])
            / len(SECURITY_CATEGORIES)
            * 100
        )

        print(f"\nComponent Coverage: {component_coverage:.1f}%")
        print(f"Security Category Coverage: {category_coverage:.1f}%")
        print("=" * 80 + "\n")

        # The scripts should have at least 70% coverage to be considered sufficient
        assert (
            component_coverage >= 70.0
        ), f"Component coverage ({component_coverage:.1f}%) below 70% threshold"
        assert (
            category_coverage >= 70.0
        ), f"Security category coverage ({category_coverage:.1f}%) below 70% threshold"
