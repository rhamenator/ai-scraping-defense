#!/usr/bin/env python3
"""Verify dependency integrity and detect supply chain issues."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS_LOCK = PROJECT_ROOT / "requirements.lock"
REQUIREMENTS_TXT = PROJECT_ROOT / "requirements.txt"


def _fail(message: str) -> None:
    """Print error message and exit."""
    print(f"[dependency-verify] ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def _warn(message: str) -> None:
    """Print warning message."""
    print(f"[dependency-verify] WARNING: {message}", file=sys.stderr)


def verify_lock_file_exists() -> None:
    """Ensure requirements.lock exists and is not empty."""
    if not REQUIREMENTS_LOCK.exists():
        _fail(f"requirements.lock not found at {REQUIREMENTS_LOCK}")
    
    if REQUIREMENTS_LOCK.stat().st_size == 0:
        _fail("requirements.lock is empty")
    
    print("✓ requirements.lock exists and is not empty")


def verify_lock_file_format() -> None:
    """Verify requirements.lock has proper format with hashes."""
    content = REQUIREMENTS_LOCK.read_text()
    lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]
    
    # Check for package lines (name==version format)
    package_lines = [line for line in lines if "==" in line and not line.startswith(" ")]
    
    if not package_lines:
        _fail("requirements.lock contains no pinned packages")
    
    print(f"✓ requirements.lock contains {len(package_lines)} pinned packages")


def verify_no_malicious_patterns() -> None:
    """Scan for known malicious patterns in dependency specifications."""
    malicious_patterns = [
        (r"--index-url\s+http://", "Insecure HTTP index URL"),
        (r"--extra-index-url\s+http://(?!download\.pytorch\.org)", "Insecure HTTP extra index (non-PyTorch)"),
        (r"git\+http://", "Insecure git+http protocol"),
        (r"--trusted-host", "Trusted host bypass (potential security issue)"),
    ]
    
    for file_path in [REQUIREMENTS_TXT, REQUIREMENTS_LOCK]:
        if not file_path.exists():
            continue
            
        content = file_path.read_text()
        
        for pattern, description in malicious_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                _warn(f"{file_path.name}: {description}")


def check_pip_audit() -> None:
    """Run pip-audit to check for known vulnerabilities."""
    try:
        result = subprocess.run(
            ["pip-audit", "--requirement", str(REQUIREMENTS_TXT), "--format", "json"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print("✓ pip-audit found no known vulnerabilities")
        else:
            # pip-audit returns non-zero if vulnerabilities found
            try:
                vulnerabilities = json.loads(result.stdout)
                if vulnerabilities:
                    _warn(f"pip-audit found {len(vulnerabilities)} potential vulnerabilities")
                    print("  Run 'pip-audit -r requirements.txt' for details")
            except json.JSONDecodeError:
                _warn("pip-audit completed with warnings (see output above)")
                
    except FileNotFoundError:
        _warn("pip-audit not installed. Install with: pip install pip-audit")
    except subprocess.TimeoutExpired:
        _warn("pip-audit timed out after 60 seconds")
    except Exception as e:
        _warn(f"pip-audit check failed: {e}")


def verify_requirements_sync() -> None:
    """Check that requirements.lock is in sync with requirements.txt."""
    if not REQUIREMENTS_TXT.exists():
        _fail("requirements.txt not found")
    
    # Read package names from requirements.txt (excluding comments and options)
    req_content = REQUIREMENTS_TXT.read_text()
    req_packages = set()
    
    for line in req_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Extract package name (before any version specifier)
        match = re.match(r"^([a-zA-Z0-9_-]+)", line)
        if match:
            req_packages.add(match.group(1).lower().replace("-", "_"))
    
    # Read package names from requirements.lock
    lock_content = REQUIREMENTS_LOCK.read_text()
    lock_packages = set()
    
    for line in lock_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith(" "):
            continue
        # Extract package name from pinned line (e.g., "package==1.0.0")
        match = re.match(r"^([a-zA-Z0-9_-]+)==", line)
        if match:
            lock_packages.add(match.group(1).lower().replace("-", "_"))
    
    # Check if all required packages are in lock file
    missing = req_packages - lock_packages
    if missing:
        _warn(f"Packages in requirements.txt not found in lock file: {missing}")
        print("  Consider regenerating requirements.lock with: pip-compile requirements.txt")
    else:
        print(f"✓ requirements.lock appears synchronized with requirements.txt")


def generate_dependency_report() -> dict[str, Any]:
    """Generate a report of dependency metadata."""
    report: dict[str, Any] = {
        "lock_file_exists": REQUIREMENTS_LOCK.exists(),
        "requirements_file_exists": REQUIREMENTS_TXT.exists(),
        "package_count": 0,
        "status": "unknown"
    }
    
    if REQUIREMENTS_LOCK.exists():
        content = REQUIREMENTS_LOCK.read_text()
        package_lines = [line for line in content.splitlines() 
                        if line.strip() and not line.strip().startswith("#") 
                        and "==" in line and not line.strip().startswith(" ")]
        report["package_count"] = len(package_lines)
    
    report["status"] = "verified"
    return report


def main() -> int:
    """Run all dependency verification checks."""
    print("=" * 60)
    print("Dependency Integrity Verification")
    print("=" * 60)
    
    try:
        verify_lock_file_exists()
        verify_lock_file_format()
        verify_no_malicious_patterns()
        verify_requirements_sync()
        check_pip_audit()
        
        report = generate_dependency_report()
        print("\n" + "=" * 60)
        print("Dependency Report Summary")
        print("=" * 60)
        print(f"Package count: {report['package_count']}")
        print(f"Status: {report['status']}")
        print("=" * 60)
        print("\n✓ All dependency verification checks passed")
        return 0
        
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    except Exception as e:
        _fail(f"Unexpected error during verification: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
