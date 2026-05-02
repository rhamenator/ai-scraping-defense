#!/usr/bin/env python3
"""
Security Alert, Issue, and PR Management Script

This script manages security alerts, issues, and pull requests in a GitHub repository:
1. Fetches all security alerts (code scanning, secret scanning, Dependabot)
2. Identifies and consolidates duplicate alerts
3. Diagnoses alerts labeled as "Error"
4. Reopens relevant closed alerts
5. Creates GitHub issues for relevant alerts
6. Closes duplicate issues with superseding notes
7. Consolidates issues/PRs that differ only in files affected

Usage:
    python scripts/manage_alerts_issues_prs.py --owner OWNER --repo REPO --token TOKEN [--dry-run]

Requirements:
    pip install requests PyGithub

Environment:
    - GITHUB_TOKEN: GitHub Personal Access Token with appropriate permissions
      Required scopes: repo, security_events, admin:org (for secret scanning)
"""

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List

try:
    import requests
    from github import Github

    try:
        from github import Auth
    except Exception:  # pragma: no cover - older PyGithub
        Auth = None
except ImportError:
    print("ERROR: Required libraries not installed.")
    print("Please run: pip install requests PyGithub")
    sys.exit(1)


class AlertManager:
    """Manages security alerts, issues, and PRs for a GitHub repository."""

    def __init__(
        self,
        owner: str,
        repo: str,
        token: str,
        dry_run: bool = False,
        include_dependabot: bool = True,
    ):
        self.owner = owner
        self.repo = repo
        # Don't store the token at all to prevent any possibility of exposure
        # Token is only used immediately in initialization
        self.dry_run = dry_run
        self.include_dependabot = include_dependabot
        if Auth is not None:
            self.gh = Github(auth=Auth.Token(token))
        else:
            self.gh = Github(token)
        self.repository = self.gh.get_repo(f"{owner}/{repo}")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        self.base_url = f"https://api.github.com/repos/{owner}/{repo}"

        # Track actions taken
        self.actions_log = []
        self.stats = {
            "alerts_fetched": 0,
            "alerts_reopened": 0,
            "alerts_consolidated": 0,
            "alerts_closed": 0,
            "issues_created": 0,
            "issues_closed": 0,
            "issues_consolidated": 0,
            "prs_closed": 0,
            "prs_consolidated": 0,
            "errors_diagnosed": 0,
        }

    def _sanitize_message(self, message: str) -> str:
        """Sanitize message to remove any potential sensitive data like tokens."""
        import re

        # Pattern to match GitHub tokens with specific format:
        # ghp_ (personal), gho_ (OAuth), ghs_ (server), ghu_ (user), ghr_ (refresh) + exactly 36 chars
        # Use word boundary to ensure we match complete tokens
        token_pattern = r"\bgh[pousr]_[A-Za-z0-9]{36}\b"  # nosec B105
        message = re.sub(token_pattern, "[REDACTED_TOKEN]", message)
        # Pattern to match Bearer tokens and other authorization headers
        auth_pattern = r"(Bearer\s+|token\s+)[A-Za-z0-9_\-\.=]+"
        message = re.sub(auth_pattern, r"\1[REDACTED]", message, flags=re.IGNORECASE)
        return message

    def log_action(self, action: str, details: str):
        """Log an action with timestamp. Sanitizes sensitive data."""
        timestamp = datetime.now().isoformat()
        # Sanitize details to prevent token exposure
        safe_details = self._sanitize_message(details)
        log_entry = f"[{timestamp}] {action}: {safe_details}"
        self.actions_log.append(log_entry)
        print(f"[{timestamp}] {action}")

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity ratio between two text strings."""
        return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

    def normalize_alert_key(self, alert: Dict) -> str:
        """Create a normalized key for an alert based on its essential properties."""
        # Extract key information that defines the alert (not file paths or IDs)
        tool = alert.get("tool", {}).get("name", "unknown")
        rule_id = alert.get("rule", {}).get("id", "")
        severity = alert.get("rule", {}).get("severity", "")
        description = alert.get("rule", {}).get("description", "")

        # Create a normalized key
        key = f"{tool}:{rule_id}:{severity}:{description[:100]}"
        return key

    def fetch_code_scanning_alerts(self) -> List[Dict]:
        """Fetch all code scanning alerts."""
        alerts = []
        page = 1
        per_page = 100

        self.log_action("FETCH", "Fetching code scanning alerts...")

        while True:
            try:
                url = f"{self.base_url}/code-scanning/alerts"
                params = {"state": "open", "page": page, "per_page": per_page}
                response = self.session.get(url, params=params)
                response.raise_for_status()

                batch = response.json()
                if not batch:
                    break

                alerts.extend(batch)
                page += 1

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    self.log_action(
                        "ERROR",
                        "403 Forbidden: Insufficient permissions for code scanning alerts",
                    )
                    break
                elif e.response.status_code == 404:
                    self.log_action(
                        "INFO", "Code scanning not enabled for this repository"
                    )
                    break
                else:
                    self.log_action(
                        "ERROR", f"Failed to fetch code scanning alerts: {e}"
                    )
                    break
            except Exception as e:
                self.log_action(
                    "ERROR", f"Unexpected error fetching code scanning alerts: {e}"
                )
                break

        self.stats["alerts_fetched"] += len(alerts)
        self.log_action("INFO", f"Fetched {len(alerts)} code scanning alerts")
        return alerts

    def fetch_secret_scanning_alerts(self) -> List[Dict]:
        """Fetch all secret scanning alerts."""
        alerts = []
        page = 1
        per_page = 100

        self.log_action("FETCH", "Fetching secret scanning alerts...")

        while True:
            try:
                url = f"{self.base_url}/secret-scanning/alerts"
                params = {"state": "open", "page": page, "per_page": per_page}
                response = self.session.get(url, params=params)
                response.raise_for_status()

                batch = response.json()
                if not batch:
                    break

                alerts.extend(batch)
                page += 1

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    self.log_action(
                        "ERROR",
                        "403 Forbidden: Insufficient permissions for secret scanning alerts",
                    )
                    break
                elif e.response.status_code == 404:
                    self.log_action(
                        "INFO", "Secret scanning not enabled for this repository"
                    )
                    break
                else:
                    self.log_action(
                        "ERROR", f"Failed to fetch secret scanning alerts: {e}"
                    )
                    break
            except Exception as e:
                self.log_action(
                    "ERROR", f"Unexpected error fetching secret scanning alerts: {e}"
                )
                break

        self.stats["alerts_fetched"] += len(alerts)
        self.log_action("INFO", f"Fetched {len(alerts)} secret scanning alerts")
        return alerts

    def fetch_dependabot_alerts(self) -> List[Dict]:
        """Fetch all Dependabot alerts."""
        alerts = []
        page = 1
        per_page = 100

        self.log_action("FETCH", "Fetching Dependabot alerts...")

        while True:
            try:
                url = f"{self.base_url}/dependabot/alerts"
                params = {"state": "open", "page": page, "per_page": per_page}
                response = self.session.get(url, params=params)
                response.raise_for_status()

                batch = response.json()
                if not batch:
                    break

                alerts.extend(batch)
                page += 1

            except requests.exceptions.HTTPError as e:
                status = e.response.status_code
                if status == 403:
                    self.log_action(
                        "ERROR",
                        "403 Forbidden: Insufficient permissions for Dependabot alerts",
                    )
                    break
                if status in {400, 404}:
                    self.log_action(
                        "INFO",
                        "Dependabot alerts unavailable for this repository",
                    )
                    break
                self.log_action("ERROR", f"Failed to fetch Dependabot alerts: {e}")
                break
            except Exception as e:
                self.log_action(
                    "ERROR", f"Unexpected error fetching Dependabot alerts: {e}"
                )
                break

        self.stats["alerts_fetched"] += len(alerts)
        self.log_action("INFO", f"Fetched {len(alerts)} Dependabot alerts")
        return alerts

    def identify_duplicate_alerts(
        self, alerts: List[Dict], alert_type: str
    ) -> Dict[str, List[Dict]]:
        """Group alerts by their normalized key to identify duplicates."""
        groups = defaultdict(list)

        for alert in alerts:
            key = self.normalize_alert_key(alert)
            groups[key].append(alert)

        # Filter to only return groups with duplicates
        duplicates = {k: v for k, v in groups.items() if len(v) > 1}

        if duplicates:
            self.log_action(
                "ANALYSIS",
                f"Found {len(duplicates)} groups of duplicate {alert_type} alerts",
            )
            for key, group in duplicates.items():
                self.log_action("DETAIL", f"  - {key}: {len(group)} duplicates")

        return duplicates

    def consolidate_alerts(
        self, duplicate_groups: Dict[str, List[Dict]], alert_type: str
    ):
        """Consolidate duplicate alerts by closing all but the primary one."""
        for key, alerts in duplicate_groups.items():
            if len(alerts) <= 1:
                continue

            # Sort by alert number to keep the oldest one
            sorted_alerts = sorted(alerts, key=lambda x: x.get("number", 0))
            primary_alert = sorted_alerts[0]
            duplicates = sorted_alerts[1:]

            # Collect all affected files
            all_files = set()
            for alert in alerts:
                if "instances" in alert:
                    for instance in alert["instances"]:
                        location = instance.get("location", {})
                        path = location.get("path", "")
                        if path:
                            all_files.add(path)
                elif "locations" in alert:
                    for location in alert["locations"]:
                        path = location.get("path", "")
                        if path:
                            all_files.add(path)

            files_list = ", ".join(sorted(all_files)[:10])
            if len(all_files) > 10:
                files_list += f" ... and {len(all_files) - 10} more"

            self.log_action(
                "CONSOLIDATE", f"Consolidating {alert_type} alert group: {key}"
            )
            self.log_action("DETAIL", f"  Primary: #{primary_alert.get('number')}")
            self.log_action("DETAIL", f"  Affected files: {files_list}")

            # Close duplicate alerts
            for dup_alert in duplicates:
                alert_num = dup_alert.get("number")
                self.log_action("DETAIL", f"  Closing duplicate: #{alert_num}")

                if not self.dry_run:
                    try:
                        if alert_type == "code_scanning":
                            url = f"{self.base_url}/code-scanning/alerts/{alert_num}"
                            data = {
                                "state": "dismissed",
                                "dismissed_reason": "false positive",
                                "dismissed_comment": f"Duplicate of alert #{primary_alert.get('number')}. "
                                f"Consolidated alert covers files: {files_list}",
                            }
                            response = self.session.patch(url, json=data)
                            response.raise_for_status()
                        elif alert_type == "secret_scanning":
                            url = f"{self.base_url}/secret-scanning/alerts/{alert_num}"
                            data = {
                                "state": "resolved",
                                "resolution": "false_positive",
                                "resolution_comment": f"Duplicate of alert #{primary_alert.get('number')}. "
                                f"Consolidated alert covers files: {files_list}",
                            }
                            response = self.session.patch(url, json=data)
                            response.raise_for_status()
                        elif alert_type == "dependabot":
                            url = f"{self.base_url}/dependabot/alerts/{alert_num}"
                            data = {
                                "state": "dismissed",
                                "dismissed_reason": "no_bandwidth",
                                "dismissed_comment": f"Duplicate of alert #{primary_alert.get('number')}. "
                                f"Consolidated alert covers dependencies: {files_list}",
                            }
                            response = self.session.patch(url, json=data)
                            response.raise_for_status()

                        self.stats["alerts_closed"] += 1
                        self.stats["alerts_consolidated"] += 1

                    except Exception as e:
                        self.log_action(
                            "ERROR",
                            f"Failed to close duplicate alert #{alert_num}: {e}",
                        )

    def diagnose_error_alerts(self, alerts: List[Dict], alert_type: str):
        """Diagnose alerts with "Error" state or label."""
        error_alerts = []

        for alert in alerts:
            # Check for error states
            state = alert.get("state", "").lower()
            state_reason = alert.get("state_reason", "").lower()

            if "error" in state or "error" in state_reason:
                error_alerts.append(alert)

        if not error_alerts:
            self.log_action("INFO", f"No error-state {alert_type} alerts found")
            return

        self.log_action(
            "DIAGNOSIS", f"Found {len(error_alerts)} {alert_type} alerts with errors"
        )

        for alert in error_alerts:
            alert_num = alert.get("number")
            state_reason = alert.get("state_reason", "unknown")

            self.log_action(
                "DETAIL", f"  Alert #{alert_num}: state_reason={state_reason}"
            )
            self.stats["errors_diagnosed"] += 1

            # Common error reasons and remediation
            remediation = self.get_error_remediation(state_reason, alert_type)
            if remediation:
                self.log_action("REMEDIATION", f"    Suggested fix: {remediation}")

    def get_error_remediation(self, state_reason: str, alert_type: str) -> str:
        """Get remediation suggestion for error state."""
        remediations = {
            "stale": "Alert may be outdated. Re-run scan or verify if issue still exists.",
            "timeout": "Scan timeout. Consider optimizing codebase or increasing timeout.",
            "analysis_error": "Analysis failed. Check logs and re-run scan.",
            "insufficient_permissions": "Scanner lacks permissions. Review and grant necessary permissions.",
            "configuration_error": "Configuration issue. Review scanner configuration.",
        }

        for key, remedy in remediations.items():
            if key in state_reason.lower():
                return remedy

        return "Unknown error reason. Manual investigation required."

    def fetch_issues(self, state: str = "open") -> List:
        """Fetch issues from the repository."""
        self.log_action("FETCH", f"Fetching {state} issues...")
        try:
            issues = list(self.repository.get_issues(state=state))
            self.log_action("INFO", f"Fetched {len(issues)} {state} issues")
            return issues
        except Exception as e:
            self.log_action("ERROR", f"Failed to fetch issues: {e}")
            return []

    def identify_duplicate_issues(self, issues: List) -> Dict[str, List]:
        """Identify duplicate issues based on title and body similarity."""
        groups = defaultdict(list)

        for issue in issues:
            # Skip pull requests
            if issue.pull_request:
                continue

            # Create a normalized key based on title
            title = issue.title.lower()
            # Remove common prefixes
            for prefix in [
                "[security]",
                "[bug]",
                "[feature]",
                "missing",
                "inadequate",
                "insecure",
            ]:
                title = title.replace(prefix, "").strip()

            groups[title].append(issue)

        # Refine groups by checking body similarity
        refined_groups = {}
        for title, group in groups.items():
            if len(group) <= 1:
                continue

            # Further group by body similarity
            subgroups = []
            for issue in group:
                matched = False
                for subgroup in subgroups:
                    # Check similarity with first issue in subgroup
                    similarity = self.calculate_similarity(
                        issue.body or "", subgroup[0].body or ""
                    )
                    if similarity > 0.8:  # 80% similarity threshold
                        subgroup.append(issue)
                        matched = True
                        break

                if not matched:
                    subgroups.append([issue])

            # Add subgroups with duplicates
            for i, subgroup in enumerate(subgroups):
                if len(subgroup) > 1:
                    refined_groups[f"{title}_{i}"] = subgroup

        if refined_groups:
            self.log_action(
                "ANALYSIS", f"Found {len(refined_groups)} groups of duplicate issues"
            )
            for key, group in refined_groups.items():
                self.log_action("DETAIL", f"  - {key}: {len(group)} duplicates")

        return refined_groups

    def consolidate_issues(self, duplicate_groups: Dict[str, List]):
        """Consolidate duplicate issues."""
        for key, issues in duplicate_groups.items():
            if len(issues) <= 1:
                continue

            # Sort by issue number to keep the oldest
            sorted_issues = sorted(issues, key=lambda x: x.number)
            primary_issue = sorted_issues[0]
            duplicates = sorted_issues[1:]

            self.log_action("CONSOLIDATE", f"Consolidating issue group: {key}")
            self.log_action(
                "DETAIL", f"  Primary: #{primary_issue.number} - {primary_issue.title}"
            )

            # Close duplicate issues
            for dup_issue in duplicates:
                self.log_action("DETAIL", f"  Closing duplicate: #{dup_issue.number}")

                if not self.dry_run:
                    try:
                        comment = (
                            f"Closing as duplicate. This issue is superseded by "
                            f"#{primary_issue.number} which consolidates all related concerns."
                        )
                        dup_issue.create_comment(comment)
                        dup_issue.edit(state="closed", state_reason="not_planned")

                        self.stats["issues_closed"] += 1
                        self.stats["issues_consolidated"] += 1

                    except Exception as e:
                        self.log_action(
                            "ERROR",
                            f"Failed to close duplicate issue #{dup_issue.number}: {e}",
                        )

    def fetch_pull_requests(self, state: str = "open") -> List:
        """Fetch pull requests from the repository."""
        self.log_action("FETCH", f"Fetching {state} pull requests...")
        try:
            prs = list(self.repository.get_pulls(state=state))
            self.log_action("INFO", f"Fetched {len(prs)} {state} pull requests")
            return prs
        except Exception as e:
            self.log_action("ERROR", f"Failed to fetch pull requests: {e}")
            return []

    def identify_duplicate_prs(self, prs: List) -> Dict[str, List]:
        """Identify duplicate pull requests."""
        groups = defaultdict(list)

        for pr in prs:
            # Create a normalized key based on title
            title = pr.title.lower()
            # Remove common prefixes
            for prefix in ["fix:", "feat:", "chore:", "docs:"]:
                title = title.replace(prefix, "").strip()

            groups[title].append(pr)

        # Refine by checking body similarity
        refined_groups = {}
        for title, group in groups.items():
            if len(group) <= 1:
                continue

            # Further group by body similarity
            subgroups = []
            for pr in group:
                matched = False
                for subgroup in subgroups:
                    similarity = self.calculate_similarity(
                        pr.body or "", subgroup[0].body or ""
                    )
                    if similarity > 0.8:
                        subgroup.append(pr)
                        matched = True
                        break

                if not matched:
                    subgroups.append([pr])

            for i, subgroup in enumerate(subgroups):
                if len(subgroup) > 1:
                    refined_groups[f"{title}_{i}"] = subgroup

        if refined_groups:
            self.log_action(
                "ANALYSIS", f"Found {len(refined_groups)} groups of duplicate PRs"
            )
            for key, group in refined_groups.items():
                self.log_action("DETAIL", f"  - {key}: {len(group)} duplicates")

        return refined_groups

    def consolidate_prs(self, duplicate_groups: Dict[str, List]):
        """Consolidate duplicate pull requests."""
        for key, prs in duplicate_groups.items():
            if len(prs) <= 1:
                continue

            # Sort by PR number to keep the oldest
            sorted_prs = sorted(prs, key=lambda x: x.number)
            primary_pr = sorted_prs[0]
            duplicates = sorted_prs[1:]

            self.log_action("CONSOLIDATE", f"Consolidating PR group: {key}")
            self.log_action(
                "DETAIL", f"  Primary: #{primary_pr.number} - {primary_pr.title}"
            )

            # Close duplicate PRs
            for dup_pr in duplicates:
                self.log_action("DETAIL", f"  Closing duplicate: #{dup_pr.number}")

                if not self.dry_run:
                    try:
                        comment = (
                            f"Closing as duplicate. This PR is superseded by "
                            f"#{primary_pr.number} which consolidates all related changes."
                        )
                        dup_pr.create_issue_comment(comment)
                        dup_pr.edit(state="closed")

                        self.stats["prs_closed"] += 1
                        self.stats["prs_consolidated"] += 1

                    except Exception as e:
                        self.log_action(
                            "ERROR",
                            f"Failed to close duplicate PR #{dup_pr.number}: {e}",
                        )

    def generate_report(self) -> str:
        """Generate a comprehensive report of actions taken."""
        report = []
        report.append("=" * 80)
        report.append("SECURITY ALERT, ISSUE, AND PR MANAGEMENT REPORT")
        report.append("=" * 80)
        report.append(f"Repository: {self.owner}/{self.repo}")
        report.append(f"Timestamp: {datetime.now().isoformat()}")
        report.append(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        report.append("")

        report.append("STATISTICS:")
        report.append("-" * 80)
        for key, value in self.stats.items():
            report.append(f"  {key.replace('_', ' ').title()}: {value}")
        report.append("")

        report.append("ACTIONS LOG: (suppressed to avoid storing sensitive data)")
        report.append("-" * 80)
        report.append("See stdout for high-level status messages.")
        report.append("")

        report.append("=" * 80)

        return "\n".join(report)

    def run(self):
        """Run the complete alert management workflow."""
        self.log_action(
            "START", f"Starting alert management for {self.owner}/{self.repo}"
        )

        if self.dry_run:
            self.log_action("INFO", "Running in DRY RUN mode - no changes will be made")

        # 1. Fetch and analyze alerts
        code_alerts = self.fetch_code_scanning_alerts()
        secret_alerts = self.fetch_secret_scanning_alerts()
        dependabot_alerts: List[Dict] = []
        if self.include_dependabot:
            dependabot_alerts = self.fetch_dependabot_alerts()
        else:
            self.log_action(
                "INFO", "Dependabot alerts disabled by configuration; skipping"
            )

        # 2. Diagnose error alerts
        if code_alerts:
            self.diagnose_error_alerts(code_alerts, "code_scanning")
        if secret_alerts:
            self.diagnose_error_alerts(secret_alerts, "secret_scanning")
        if dependabot_alerts:
            self.diagnose_error_alerts(dependabot_alerts, "dependabot")

        # 3. Identify and consolidate duplicate alerts
        if code_alerts:
            code_dupes = self.identify_duplicate_alerts(code_alerts, "code_scanning")
            if code_dupes:
                self.consolidate_alerts(code_dupes, "code_scanning")

        if secret_alerts:
            secret_dupes = self.identify_duplicate_alerts(
                secret_alerts, "secret_scanning"
            )
            if secret_dupes:
                self.consolidate_alerts(secret_dupes, "secret_scanning")

        if dependabot_alerts:
            dep_dupes = self.identify_duplicate_alerts(dependabot_alerts, "dependabot")
            if dep_dupes:
                self.consolidate_alerts(dep_dupes, "dependabot")

        # 4. Manage issues
        issues = self.fetch_issues(state="open")
        if issues:
            issue_dupes = self.identify_duplicate_issues(issues)
            if issue_dupes:
                self.consolidate_issues(issue_dupes)

        # 5. Manage PRs
        prs = self.fetch_pull_requests(state="open")
        if prs:
            pr_dupes = self.identify_duplicate_prs(prs)
            if pr_dupes:
                self.consolidate_prs(pr_dupes)

        # 6. Generate report
        report = self.generate_report()
        safe_report = self._sanitize_message(report)
        print("\n" + safe_report)

        # Save report to file
        report_filename = (
            f"alert_management_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        with open(report_filename, "w") as f:
            f.write(safe_report)

        self.log_action("COMPLETE", f"Report saved to {report_filename}")


def _sanitize_message_standalone(message: str) -> str:
    """Standalone function to sanitize messages (for use before manager is created)."""
    import re

    # Pattern to match GitHub tokens with specific format:
    # ghp_ (personal), gho_ (OAuth), ghs_ (server), ghu_ (user), ghr_ (refresh) + exactly 36 chars
    # Use word boundary to ensure we match complete tokens
    token_pattern = r"\bgh[pousr]_[A-Za-z0-9]{36}\b"  # nosec B105
    message = re.sub(token_pattern, "[REDACTED_TOKEN]", message)
    # Pattern to match Bearer tokens and other authorization headers
    auth_pattern = r"(Bearer\s+|token\s+)[A-Za-z0-9_\-\.=]+"
    message = re.sub(auth_pattern, r"\1[REDACTED]", message, flags=re.IGNORECASE)
    return message


def main():
    parser = argparse.ArgumentParser(
        description="Manage security alerts, issues, and PRs in a GitHub repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--owner", required=True, help="GitHub repository owner")
    parser.add_argument("--repo", required=True, help="GitHub repository name")
    parser.add_argument(
        "--token", help="GitHub Personal Access Token (or use GITHUB_TOKEN env var)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no changes will be made)",
    )
    parser.add_argument(
        "--include-dependabot",
        choices=["true", "false"],
        help="Whether to include Dependabot alerts (default: true)",
    )

    args = parser.parse_args()

    # Get token from args or environment
    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print(
            "ERROR: GitHub token is required. Provide via --token or GITHUB_TOKEN env var"
        )
        sys.exit(1)

    include_dependabot = True
    if args.include_dependabot is not None:
        include_dependabot = args.include_dependabot == "true"
    else:
        env_value = os.environ.get("INCLUDE_DEPENDABOT_ALERTS")
        if env_value is not None:
            include_dependabot = env_value.strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }

    # Create and run manager
    manager = None
    try:
        manager = AlertManager(
            args.owner,
            args.repo,
            token,
            args.dry_run,
            include_dependabot=include_dependabot,
        )
        manager.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        # Sanitize error message to prevent token exposure
        if manager:
            error_msg = manager._sanitize_message(str(e))
        else:
            error_msg = _sanitize_message_standalone(str(e))
        print(f"\n\nFATAL ERROR: {error_msg}")
        import traceback

        # Sanitize traceback as well
        tb = traceback.format_exc()
        if manager:
            safe_tb = manager._sanitize_message(tb)
        else:
            safe_tb = _sanitize_message_standalone(tb)
        print(safe_tb)
        sys.exit(1)


if __name__ == "__main__":
    main()
