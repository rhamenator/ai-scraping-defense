#!/usr/bin/env python3
"""
Script to create GitHub issues for all code scanning alerts.

This script processes code scanning results from various tools (Bandit, Flake8, etc.)
and creates GitHub issues for each unique finding.
"""

import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List


def load_bandit_results(filepath: str) -> List[Dict[str, Any]]:
    """Load Bandit scan results from JSON file."""
    try:
        with open(filepath, "r") as f:
            data = json.load(f)
            return data.get("results", [])
    except Exception as e:
        print(f"Error loading Bandit results: {e}")
        return []


def group_bandit_issues(
    results: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """Group Bandit issues by test ID for easier issue creation."""
    grouped = defaultdict(list)
    for result in results:
        test_id = result.get("test_id", "UNKNOWN")
        grouped[test_id].append(result)
    return dict(grouped)


def create_github_issue(title: str, body: str, labels: List[str]) -> bool:
    """Create a GitHub issue using gh CLI."""
    try:
        # Check if gh CLI is available
        subprocess.run(  # nosec B603 - controlled gh CLI call
            ["gh", "--version"], capture_output=True, check=True
        )

        # Create the issue
        cmd = ["gh", "issue", "create", "--title", title, "--body", body]
        for label in labels:
            cmd.extend(["--label", label])

        result = subprocess.run(  # nosec B603 - controlled gh CLI call
            cmd, capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"✓ Created issue: {title}")
            return True
        else:
            print(f"✗ Failed to create issue: {title}")
            print(f"  Error: {result.stderr}")
            return False
    except Exception as e:
        print(f"✗ Error creating issue '{title}': {e}")
        return False


def generate_bandit_issue_body(test_id: str, issues: List[Dict[str, Any]]) -> str:
    """Generate issue body for grouped Bandit findings."""
    first_issue = issues[0]
    test_name = first_issue.get("test_name", "Unknown")
    severity = first_issue.get("issue_severity", "UNKNOWN")
    confidence = first_issue.get("issue_confidence", "UNKNOWN")
    more_info = first_issue.get("more_info", "")

    body = f"""## Security Issue: {test_name} ({test_id})

**Severity:** {severity}
**Confidence:** {confidence}

### Description
{first_issue.get('issue_text', 'No description available')}

### Affected Locations
Found in {len(issues)} location(s):

"""

    for issue in issues[:10]:  # Limit to first 10 occurrences in the issue body
        filename = issue.get("filename", "unknown")
        line_number = issue.get("line_number", 0)
        body += f"- `{filename}:{line_number}`\n"

    if len(issues) > 10:
        body += f"\n... and {len(issues) - 10} more occurrences\n"

    body += f"\n### More Information\n{more_info}\n"
    body += "\n### Remediation\n"
    body += "Please review the affected code and apply appropriate fixes based on the security guidelines.\n"

    if test_id == "B110":
        body += "\n**Specific Guidance for B110 (try-except-pass):**\n"
        body += "- Consider logging the exception or handling it more explicitly\n"
        body += "- If the exception is truly expected and can be ignored, add a comment explaining why\n"
        body += "- Consider using more specific exception types instead of bare `except Exception:`\n"

    return body


def main():
    """Main function to create GitHub issues for code scanning alerts."""
    print("Creating GitHub issues for code scanning alerts...")

    # Check if GH_TOKEN is set
    if not os.environ.get("GH_TOKEN"):
        print("WARNING: GH_TOKEN environment variable not set.")
        print(
            "Issue creation will fail. This is expected in the automated environment."
        )
        print("Generating issue report instead...\n")
        create_report = True
    else:
        create_report = False

    # Load Bandit results
    bandit_file = "/tmp/bandit-results.json"
    if not Path(bandit_file).exists():
        print(f"Bandit results file not found: {bandit_file}")
        print("Run: bandit -r src/ -f json -o /tmp/bandit-results.json")
        return 1

    bandit_results = load_bandit_results(bandit_file)
    print(f"Found {len(bandit_results)} Bandit findings")

    # Group Bandit issues
    grouped_issues = group_bandit_issues(bandit_results)
    print(f"Grouped into {len(grouped_issues)} unique issue types\n")

    # Create issues or generate report
    created_count = 0
    failed_count = 0

    report_lines = []
    report_lines.append("# Code Scanning Issues Report\n")
    report_lines.append(f"Total findings: {len(bandit_results)}\n")
    report_lines.append(f"Unique issue types: {len(grouped_issues)}\n\n")

    for test_id, issues in sorted(grouped_issues.items()):
        first_issue = issues[0]
        severity = first_issue.get("issue_severity", "UNKNOWN")
        title = (
            f"[Codacy] {test_id}: {first_issue.get('test_name', 'Unknown')} "
            f"({len(issues)} occurrences, Severity: {severity})"
        )
        body = generate_bandit_issue_body(test_id, issues)

        labels = ["security", "code-quality", "automated"]
        if severity == "HIGH":
            labels.append("priority-high")
        elif severity == "MEDIUM":
            labels.append("priority-medium")
        else:
            labels.append("priority-low")

        if create_report:
            report_lines.append(f"\n## {title}\n")
            report_lines.append(body)
            report_lines.append("\n---\n")
        else:
            if create_github_issue(title, body, labels):
                created_count += 1
            else:
                failed_count += 1

    if create_report:
        report_file = "CODE_SCANNING_ISSUES.md"
        with open(report_file, "w") as f:
            f.writelines(report_lines)
        print(f"\n✓ Generated report: {report_file}")
        print(f"  Contains {len(grouped_issues)} issue types")
    else:
        print(f"\n{'='*60}")
        print("Summary:")
        print(f"  ✓ Created: {created_count} issues")
        print(f"  ✗ Failed:  {failed_count} issues")
        print(f"{'='*60}")

    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
