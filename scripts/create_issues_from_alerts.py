#!/usr/bin/env python3
"""
Create GitHub Issues from Code Scanning, Secret Scanning, and Dependabot Alerts

This script fetches all open code scanning, secret scanning, and Dependabot alerts from a GitHub
repository and creates corresponding GitHub issues for each alert (or group of similar alerts).

Usage:
    python scripts/create_issues_from_alerts.py --owner OWNER --repo REPO [--dry-run]

Requirements:
    pip install requests PyGithub

Environment:
    - GITHUB_TOKEN: GitHub Personal Access Token with appropriate permissions
      Required scopes: repo, security_events

Features:
    - Fetches all open code scanning alerts
    - Fetches all open secret scanning alerts
    - Fetches all open Dependabot alerts (GraphQL; does not require security_events scope)
    - Groups similar alerts to avoid creating duplicate issues
    - Creates well-formatted GitHub issues with:
      - Clear titles
      - Detailed descriptions
      - Affected file locations
      - Remediation guidance
      - Appropriate labels
    - Supports dry-run mode to preview what would be created
    - Checks for existing issues to avoid duplicates
"""

import argparse
import os
import re
import sys
import traceback
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import requests

try:
    from github import Github

    try:
        from github import Auth
    except Exception:  # pragma: no cover - older PyGithub
        Auth = None
except ImportError:  # pragma: no cover
    # This script is used by workflows that install PyGithub explicitly, but
    # the wider repo/test environment may not include it by default.
    Github = None
    Auth = None

# Configuration constants
SIGNATURE_SEARCH_WORDS = 3  # Number of words from signature to use in search query
SECURITY_SEVERITY_ORDER = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


class IssueCreator:
    """Creates GitHub issues from security scanning alerts."""

    def __init__(
        self,
        owner: str,
        repo: str,
        token: str,
        dry_run: bool = False,
        min_security_severity: Optional[str] = None,
        include_dependabot: bool = False,
    ):
        if Github is None:
            raise RuntimeError(
                "PyGithub is required to use IssueCreator. "
                "Install with: pip install PyGithub"
            )
        self.owner = owner
        self.repo = repo
        self.dry_run = dry_run
        self.include_dependabot = include_dependabot
        self.min_security_severity = (
            min_security_severity.lower()
            if isinstance(min_security_severity, str)
            else None
        )
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

        # Cache open issues once to avoid GitHub Search API abuse limits.
        self._existing_by_dedupe_key = None
        self._existing_by_signature = None
        self._existing_by_code_rule_id = None
        self._existing_by_secret_type = None

        # Track statistics
        self.stats = {
            "code_scanning_alerts": 0,
            "secret_scanning_alerts": 0,
            "dependabot_alerts": 0,
            "issues_created": 0,
            "issues_skipped_existing": 0,
        }

    def _passes_min_security_severity_level(self, level: str) -> bool:
        """Return True if a severity label meets the configured threshold."""
        if not self.min_security_severity:
            return True
        threshold = SECURITY_SEVERITY_ORDER.get(self.min_security_severity, 0)
        rank = SECURITY_SEVERITY_ORDER.get(str(level).lower(), 0)
        return rank >= threshold

    def _passes_min_security_severity(self, alert: Dict) -> bool:
        """Return True if a code scanning alert meets the minimum severity."""
        rule = alert.get("rule", {})
        level = rule.get("security_severity_level", "")
        return self._passes_min_security_severity_level(str(level))

    def log(self, level: str, message: str) -> None:
        """Log a message with timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    @staticmethod
    def _slug_component(value: str) -> str:
        """Normalize a string for use in a dedupe key (no spaces)."""
        value = str(value or "").strip()
        value = re.sub(r"\s+", "_", value)
        return value or "unknown"

    def _dedupe_key_for_code_scanning(self, alerts: List[Dict]) -> str:
        first_alert = alerts[0]
        rule = first_alert.get("rule", {})
        rule_id = rule.get("id", "unknown")
        severity = rule.get("severity", "unknown")
        tool_name = first_alert.get("tool", {}).get("name", "unknown")
        tool_slug = self._slug_component(tool_name)
        return f"code-scanning:{tool_slug}:{rule_id}:{severity}"

    def _dedupe_key_for_secret_scanning(self, alerts: List[Dict]) -> str:
        first_alert = alerts[0]
        secret_type = first_alert.get("secret_type", "unknown")
        return f"secret-scanning:{self._slug_component(secret_type)}"

    def _dedupe_key_for_dependabot(self, alerts: List[Dict]) -> str:
        first_alert = alerts[0]
        advisory = first_alert.get("securityAdvisory") or {}
        ghsa_id = advisory.get("ghsaId") or "unknown"
        return f"dependabot:{self._slug_component(ghsa_id)}"

    def _load_existing_issue_cache(self) -> None:
        if self._existing_by_dedupe_key is not None:
            return
        self.log("INFO", "Loading open issues cache for dedupe...")

        existing_by_dedupe_key = {}
        existing_by_signature = {}
        existing_by_code_rule_id = {}
        existing_by_secret_type = {}
        marker_re = re.compile(r"alert-group-key:\s*(.+?)\s*(?:-->|$)")
        rule_id_re = re.compile(r"\*\*Rule ID:\*\*\s*`([^`]+)`")
        secret_type_re = re.compile(r"\*\*Secret Type:\*\*\s*`([^`]+)`")

        for issue in self.repository.get_issues(state="open"):
            sig = self.extract_issue_signature(issue.title).lower()
            existing_by_signature.setdefault(sig, issue)
            body = issue.body or ""
            match = marker_re.search(body)
            if match:
                key = match.group(1).strip()
                existing_by_dedupe_key.setdefault(key, issue)
            match = rule_id_re.search(body)
            if match:
                existing_by_code_rule_id.setdefault(match.group(1).strip(), issue)
            match = secret_type_re.search(body)
            if match:
                existing_by_secret_type.setdefault(match.group(1).strip(), issue)

        self._existing_by_dedupe_key = existing_by_dedupe_key
        self._existing_by_signature = existing_by_signature
        self._existing_by_code_rule_id = existing_by_code_rule_id
        self._existing_by_secret_type = existing_by_secret_type

    def _graphql(self, query: str, variables: Dict) -> Dict:
        resp = self.session.post(
            "https://api.github.com/graphql",
            json={"query": query, "variables": variables},
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("errors"):
            raise RuntimeError(payload["errors"])
        return payload.get("data") or {}

    def fetch_dependabot_alerts(self) -> List[Dict]:
        """Fetch open Dependabot vulnerability alerts via GraphQL."""
        self.log("INFO", "Fetching Dependabot alerts (GraphQL)...")
        alerts: List[Dict] = []

        query = """
        query($owner:String!, $name:String!, $cursor:String) {
          repository(owner:$owner, name:$name) {
            vulnerabilityAlerts(first:100, after:$cursor, states:OPEN) {
              pageInfo { hasNextPage endCursor }
              nodes {
                createdAt
                vulnerableManifestFilename
                vulnerableRequirements
                securityAdvisory {
                  ghsaId
                  summary
                  severity
                  permalink
                }
                securityVulnerability {
                  severity
                  vulnerableVersionRange
                  firstPatchedVersion { identifier }
                  package { name ecosystem }
                }
              }
            }
          }
        }
        """

        cursor = None
        try:
            while True:
                data = self._graphql(
                    query,
                    {"owner": self.owner, "name": self.repo, "cursor": cursor},
                )
                repo = data.get("repository") or {}
                vulns = repo.get("vulnerabilityAlerts") or {}
                nodes = vulns.get("nodes") or []
                alerts.extend(nodes)
                page = vulns.get("pageInfo") or {}
                if not page.get("hasNextPage"):
                    break
                cursor = page.get("endCursor")
        except requests.exceptions.HTTPError as e:
            if getattr(e.response, "status_code", None) == 403:
                self.log("WARNING", "Dependabot alerts not accessible (403 Forbidden)")
            else:
                self.log("ERROR", f"Failed to fetch Dependabot alerts: {e}")
            return []
        except Exception as e:
            self.log("ERROR", f"Error fetching Dependabot alerts ({type(e).__name__})")
            return []

        self.stats["dependabot_alerts"] = len(alerts)
        self.log("INFO", "Dependabot alerts fetched")
        return alerts

    def fetch_code_scanning_alerts(self) -> List[Dict]:
        """Fetch all open code scanning alerts."""
        self.log("INFO", "Fetching code scanning alerts...")
        alerts = []

        try:
            url = f"{self.base_url}/code-scanning/alerts"
            params = {"state": "open", "per_page": 100}

            while url:
                response = self.session.get(url, params=params)
                response.raise_for_status()
                page_alerts = response.json()
                alerts.extend(page_alerts)

                # Check for pagination
                if "next" in response.links:
                    url = response.links["next"]["url"]
                    params = {}  # URL already has params
                else:
                    url = None

            self.stats["code_scanning_alerts"] = len(alerts)
            self.log("INFO", "Code scanning alerts fetched")
            return alerts

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                self.log(
                    "WARNING", "Code scanning alerts not accessible (403 Forbidden)"
                )
                self.log(
                    "INFO",
                    "This may be due to: permissions, feature not enabled, or organization settings",
                )
            elif e.response.status_code == 404:
                self.log("INFO", "Code scanning not enabled for this repository")
            else:
                status_code = getattr(e.response, "status_code", "unknown")
                self.log(
                    "ERROR",
                    f"Failed to fetch code scanning alerts (HTTP {status_code})",
                )
            return []
        except Exception as e:
            self.log(
                "ERROR",
                f"Error fetching code scanning alerts ({type(e).__name__})",
            )
            return []

    def fetch_secret_scanning_alerts(self) -> List[Dict]:
        """Fetch all open secret scanning alerts."""
        self.log("INFO", "Fetching secret scanning alerts...")
        alerts = []

        try:
            url = f"{self.base_url}/secret-scanning/alerts"
            params = {"state": "open", "per_page": 100}

            while url:
                response = self.session.get(url, params=params)
                response.raise_for_status()
                page_alerts = response.json()
                alerts.extend(page_alerts)

                # Check for pagination
                if "next" in response.links:
                    url = response.links["next"]["url"]
                    params = {}
                else:
                    url = None

            self.stats["secret_scanning_alerts"] = len(alerts)
            self.log("INFO", "Secret scanning alerts fetched")
            return alerts

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                self.log(
                    "WARNING", "Secret scanning alerts not accessible (403 Forbidden)"
                )
                self.log(
                    "INFO",
                    "This may be due to: permissions, feature not enabled, or organization settings",
                )
            elif e.response.status_code == 404:
                self.log("INFO", "Secret scanning not enabled for this repository")
            else:
                status_code = getattr(e.response, "status_code", "unknown")
                self.log(
                    "ERROR",
                    f"Failed to fetch secret scanning alerts (HTTP {status_code})",
                )
            return []
        except Exception as e:
            self.log(
                "ERROR",
                f"Error fetching secret scanning alerts ({type(e).__name__})",
            )
            return []

    def group_code_scanning_alerts(self, alerts: List[Dict]) -> Dict[str, List[Dict]]:
        """Group code scanning alerts by rule ID and severity."""
        grouped = defaultdict(list)

        for alert in alerts:
            rule = alert.get("rule", {})
            rule_id = rule.get("id", "unknown")
            severity = rule.get("severity", "unknown")
            tool_name = alert.get("tool", {}).get("name", "unknown")

            # Create a key that groups similar alerts
            key = f"{tool_name}:{rule_id}:{severity}"
            grouped[key].append(alert)

        return dict(grouped)

    def group_secret_scanning_alerts(self, alerts: List[Dict]) -> Dict[str, List[Dict]]:
        """Group secret scanning alerts by secret type."""
        grouped = defaultdict(list)

        for alert in alerts:
            secret_type = alert.get("secret_type", "unknown")
            secret_type_display = alert.get("secret_type_display_name", secret_type)

            # Create a key for grouping
            key = f"{secret_type}:{secret_type_display}"
            grouped[key].append(alert)

        return dict(grouped)

    def group_dependabot_alerts(self, alerts: List[Dict]) -> Dict[str, List[Dict]]:
        """Group Dependabot alerts by GHSA ID."""
        grouped = defaultdict(list)
        for alert in alerts:
            ghsa_id = ((alert.get("securityAdvisory") or {}).get("ghsaId")) or "unknown"
            grouped[ghsa_id].append(alert)
        return dict(grouped)

    def create_issue_title_for_code_scanning(self, key: str, alerts: List[Dict]) -> str:
        """Generate issue title for code scanning alert group."""
        first_alert = alerts[0]
        rule = first_alert.get("rule", {})
        rule_id = rule.get("id", "unknown")
        rule_name = rule.get("name", rule_id)
        severity = rule.get("severity", "unknown").upper()
        tool_name = first_alert.get("tool", {}).get("name", "CodeQL")

        # Include rule_id to avoid collapsing different rules with similar display names.
        if str(rule_name).strip() and str(rule_name).strip() != str(rule_id).strip():
            rule_display = f"{rule_id}: {rule_name}"
        else:
            rule_display = str(rule_id)

        if len(alerts) == 1:
            return f"[Security] {tool_name}: {rule_display} ({severity})"
        else:
            return (
                f"[Security] {tool_name}: {rule_display} - "
                f"{len(alerts)} occurrences ({severity})"
            )

    def create_issue_body_for_code_scanning(self, alerts: List[Dict]) -> str:
        """Generate issue body for code scanning alert group."""
        first_alert = alerts[0]
        rule = first_alert.get("rule", {})

        # Extract rule information
        rule_id = rule.get("id", "unknown")
        rule_name = rule.get("name", rule_id)
        description = rule.get("description", "No description available")
        severity = rule.get("severity", "unknown")
        security_severity = rule.get("security_severity_level", "N/A")
        help_text = rule.get("help", "")
        alert_group_key = self._dedupe_key_for_code_scanning(alerts)

        # Build the issue body
        body = f"""<!-- alert-group-key: {alert_group_key} -->

## Security Alert: {rule_name}

**Rule ID:** `{rule_id}`
**Severity:** {severity.upper()}
**Security Severity:** {security_severity}

### Description
{description}

### Affected Locations
This alert was found in {len(alerts)} location(s):

"""

        # Add locations (limit to first 20 to keep issue manageable)
        for i, alert in enumerate(alerts[:20], 1):
            alert_num = alert.get("number", "N/A")
            location = alert.get("most_recent_instance", {}).get("location", {})
            path = location.get("path", "unknown")
            start_line = location.get("start_line")
            end_line = location.get("end_line")

            # Format line reference if line numbers are available
            if start_line is not None and end_line is not None:
                line_ref = (
                    f":{start_line}"
                    if start_line == end_line
                    else f":{start_line}-{end_line}"
                )
            elif start_line is not None:
                line_ref = f":{start_line}"
            else:
                line_ref = ""

            # Link to the alert
            alert_url = alert.get("html_url", "")
            body += f"{i}. [`{path}{line_ref}`]({alert_url}) - Alert #{alert_num}\n"

        if len(alerts) > 20:
            body += f"\n... and {len(alerts) - 20} more occurrences\n"

        # Add help/remediation guidance
        if help_text:
            body += f"\n### Guidance\n{help_text}\n"

        body += """
### Next Steps
1. Review the affected code locations
2. Understand the security implications
3. Apply appropriate fixes based on the guidance
4. Test the changes thoroughly
5. Close this issue once all occurrences are resolved

### References
"""

        # Add reference to first alert
        first_alert_url = first_alert.get("html_url", "")
        if first_alert_url:
            body += f"- [View Alert #{first_alert.get('number')}]({first_alert_url})\n"

        return body

    def create_issue_title_for_secret_scanning(
        self, key: str, alerts: List[Dict]
    ) -> str:
        """Generate issue title for secret scanning alert group."""
        first_alert = alerts[0]
        secret_type_display = first_alert.get("secret_type_display_name", "Secret")

        if len(alerts) == 1:
            return f"[Secret] Exposed {secret_type_display} detected"
        else:
            return f"[Secret] {len(alerts)} exposed {secret_type_display} detected"

    def create_issue_body_for_secret_scanning(self, alerts: List[Dict]) -> str:
        """Generate issue body for secret scanning alert group."""
        first_alert = alerts[0]
        secret_type = first_alert.get("secret_type", "unknown")
        secret_type_display = first_alert.get("secret_type_display_name", secret_type)
        alert_group_key = self._dedupe_key_for_secret_scanning(alerts)

        body = f"""<!-- alert-group-key: {alert_group_key} -->

## Secret Scanning Alert: {secret_type_display}

**Secret Type:** `{secret_type}`
**Number of Locations:** {len(alerts)}

### ⚠️ CRITICAL: Immediate Action Required

Secret scanning has detected exposed credentials in this repository.
This is a critical security issue that must be addressed immediately.

### Affected Locations

"""

        # Add locations
        for i, alert in enumerate(alerts[:20], 1):
            alert_num = alert.get("number", "N/A")
            locations = alert.get("locations", [])

            for location in locations[:3]:  # Show first 3 locations per alert
                details = location.get("details", {})
                path = details.get("path", "unknown")
                start_line = details.get("start_line")

                # Format line reference if available
                line_ref = f":{start_line}" if start_line is not None else ""
                alert_url = alert.get("html_url", "")
                body += (
                    f"{i}. [`{path}{line_ref}`]({alert_url}) - " f"Alert #{alert_num}\n"
                )

        if len(alerts) > 20:
            body += f"\n... and {len(alerts) - 20} more locations\n"

        body += """
### Immediate Actions Required

1. **REVOKE** the exposed credentials immediately
2. **ROTATE** to new credentials with proper security
3. **AUDIT** access logs for potential unauthorized access
4. **UPDATE** all systems using these credentials
5. **VERIFY** no other copies exist in git history

### Remediation Steps

1. Revoke the compromised credentials in the service provider
2. Generate new credentials following security best practices
3. Update applications/services with new credentials
4. Use secrets management (e.g., GitHub Secrets, AWS Secrets Manager, HashiCorp Vault)
5. Review git history and consider BFG Repo-Cleaner if needed
6. Add the file pattern to `.gitignore` to prevent future exposure
7. Enable commit signing and secret scanning push protection

### Prevention

- Never commit credentials to version control
- Use environment variables or secrets management systems
- Enable GitHub's secret scanning push protection
- Use `.gitignore` for sensitive files
- Implement pre-commit hooks to detect secrets
"""
        body += (
            "\n### References\n"
            "- [GitHub Secret Scanning Documentation]"
            "(https://docs.github.com/en/code-security/secret-scanning)\n"
            "- [Removing Sensitive Data from a Repository]"
            "(https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/"
            "removing-sensitive-data-from-a-repository)\n"
        )

        return body

    def create_issue_title_for_dependabot(
        self, ghsa_id: str, alerts: List[Dict]
    ) -> str:
        advisory = alerts[0].get("securityAdvisory") or {}
        vuln = alerts[0].get("securityVulnerability") or {}
        severity = (
            vuln.get("severity") or advisory.get("severity") or "unknown"
        ).lower()
        pkg = (vuln.get("package") or {}).get("name")
        summary = advisory.get("summary") or "Dependabot alert"
        if pkg:
            return f"[Dependabot] {severity}: {pkg} ({ghsa_id})"
        return f"[Dependabot] {severity}: {summary} ({ghsa_id})"

    def create_issue_body_for_dependabot(self, alerts: List[Dict]) -> str:
        advisory = alerts[0].get("securityAdvisory") or {}
        vuln = alerts[0].get("securityVulnerability") or {}

        ghsa_id = advisory.get("ghsaId") or "unknown"
        severity = (
            vuln.get("severity") or advisory.get("severity") or "unknown"
        ).lower()
        summary = advisory.get("summary") or ""
        advisory_url = advisory.get("permalink") or ""

        pkg = (vuln.get("package") or {}).get("name", "unknown")
        ecosystem = (vuln.get("package") or {}).get("ecosystem", "unknown")
        vuln_range = vuln.get("vulnerableVersionRange") or "unknown"
        fixed = (vuln.get("firstPatchedVersion") or {}).get("identifier") or "unknown"

        manifests = sorted(
            {a.get("vulnerableManifestFilename") or "unknown" for a in alerts}
        )

        body_lines = [
            f"<!-- alert-group-key: {self._dedupe_key_for_dependabot(alerts)} -->",
            "",
            "## Dependabot Alert",
            "",
            f"**GHSA ID:** `{ghsa_id}`",
            f"**Package:** `{pkg}` ({ecosystem})",
            f"**Severity:** `{severity}`",
            f"**Vulnerable Range:** `{vuln_range}`",
            f"**First Patched Version:** `{fixed}`",
        ]
        if advisory_url:
            body_lines.append(f"**Advisory:** {advisory_url}")
        if summary:
            body_lines.extend(["", "**Summary**", summary])

        body_lines.extend(["", "**Affected Manifests**"])
        body_lines.extend([f"- `{m}`" for m in manifests])

        body_lines.extend(
            [
                "",
                "**Recommended Fix**",
                f"- Upgrade `{pkg}` to at least `{fixed}` (or otherwise remediate the advisory).",
            ]
        )
        return "\n".join(body_lines)

    def extract_issue_signature(self, title: str) -> str:
        """
        Extract a signature from issue title for duplicate detection.

        Removes decorative elements like prefixes, counts, and severities
        to get the core identifying part of the issue title.

        Examples:
            Input:  "[Security] CodeQL: SQL Injection - 5 occurrences (HIGH)"
            Output: "CodeQL: SQL Injection"

            Input:  "[Codacy] B104: hardcoded_bind_all_interfaces - 2 occurrences (MEDIUM)"
            Output: "B104: hardcoded_bind_all_interfaces"

            Input:  "[Security] Bandit: try_except_pass (LOW)"
            Output: "Bandit: try_except_pass"

        Note: The signature preserves the core problem description while removing
        counts, severity indicators, and common prefixes to enable accurate matching
        of similar issues regardless of how many occurrences or what severity.

        Returns:
            str: The cleaned signature for matching
        """
        # Remove common prefixes
        signature = title
        for prefix in ["[Security]", "[Secret]", "[Codacy]", "[CodeQL]"]:
            signature = signature.replace(prefix, "")

        # Remove count patterns like "- 5 occurrences"
        signature = re.sub(r"-\s*\d+\s+occurrence[s]?", "", signature)
        signature = re.sub(
            r"\(\s*(HIGH|MEDIUM|LOW|CRITICAL)\s*\)", "", signature, flags=re.IGNORECASE
        )

        # Clean up and return
        return signature.strip()

    def check_existing_issue(
        self, title: str, *, dedupe_key: Optional[str] = None
    ) -> Optional[object]:
        """
        Check if an issue with similar title already exists.

        Uses a signature-based approach to detect duplicates even when
        titles have different formatting or counts.
        """
        try:
            self._load_existing_issue_cache()

            if dedupe_key:
                existing = self._existing_by_dedupe_key.get(dedupe_key)
                if existing:
                    return existing
                if dedupe_key.startswith("code-scanning:"):
                    # Back-compat: older issues may not have a marker but do include Rule ID.
                    parts = dedupe_key.split(":", 3)
                    if len(parts) >= 3:
                        rule_id = parts[2]
                        existing = self._existing_by_code_rule_id.get(rule_id)
                        if existing:
                            return existing
                if dedupe_key.startswith("secret-scanning:"):
                    secret_type = dedupe_key.split(":", 1)[1]
                    existing = self._existing_by_secret_type.get(secret_type)
                    if existing:
                        return existing

            signature = self.extract_issue_signature(title).lower()
            return self._existing_by_signature.get(signature)
        except Exception as e:
            self.log(
                "WARNING",
                f"Error checking for existing issue ({type(e).__name__})",
            )
            return None

    def create_github_issue(
        self,
        title: str,
        body: str,
        labels: List[str],
        *,
        dedupe_key: Optional[str] = None,
    ) -> bool:
        """Create a GitHub issue."""
        try:
            # Check if similar issue already exists
            existing = self.check_existing_issue(title, dedupe_key=dedupe_key)
            if existing:
                self.log("SKIP", f"Issue already exists: #{existing.number}")
                self.stats["issues_skipped_existing"] += 1
                return False

            if self.dry_run:
                # Avoid logging potentially sensitive issue titles in clear text
                self.log("DRY-RUN", "Would create issue (title redacted)")
                self.log("DRY-RUN", "Labels redacted")
                self.stats["issues_created"] += 1
                return True

            # Create the issue
            issue = self.repository.create_issue(title=title, body=body, labels=labels)

            self.log("SUCCESS", f"Created issue #{issue.number}")
            self.stats["issues_created"] += 1
            return True

        except Exception as e:
            self.log("ERROR", f"Failed to create issue ({type(e).__name__})")
            return False

    def process_code_scanning_alerts(self, alerts: List[Dict]):
        """Process code scanning alerts and create issues."""
        if not alerts:
            self.log("INFO", "No code scanning alerts to process")
            return

        self.log("INFO", "Processing code scanning alerts...")
        filtered_alerts = [a for a in alerts if self._passes_min_security_severity(a)]
        if len(filtered_alerts) != len(alerts):
            self.log("INFO", "Filtered alerts by min security severity")

        # Group alerts
        grouped = self.group_code_scanning_alerts(filtered_alerts)
        self.log("INFO", "Grouped code scanning alerts")

        # Create issues for each group
        for key, alert_group in grouped.items():
            title = self.create_issue_title_for_code_scanning(key, alert_group)
            body = self.create_issue_body_for_code_scanning(alert_group)

            # Determine labels
            first_alert = alert_group[0]
            rule = first_alert.get("rule", {})
            security_severity = str(rule.get("security_severity_level", "")).lower()
            severity = str(rule.get("severity", "")).lower()

            labels = ["security", "code-scanning"]

            if security_severity:
                if security_severity in {"critical", "high"}:
                    labels.append("priority: high")
                elif security_severity == "medium":
                    labels.append("priority: medium")
                else:
                    labels.append("priority: low")
            else:
                if severity == "error" or severity == "critical":
                    labels.append("priority: high")
                elif severity == "warning" or severity == "high":
                    labels.append("priority: medium")
                else:
                    labels.append("priority: low")

            # Create the issue
            self.create_github_issue(
                title,
                body,
                labels,
                dedupe_key=self._dedupe_key_for_code_scanning(alert_group),
            )

    def process_secret_scanning_alerts(self, alerts: List[Dict]):
        """Process secret scanning alerts and create issues."""
        if not alerts:
            self.log("INFO", "No secret scanning alerts to process")
            return

        self.log("INFO", "Processing secret scanning alerts...")

        # Group alerts
        grouped = self.group_secret_scanning_alerts(alerts)
        self.log("INFO", "Grouped secret scanning alerts")

        # Create issues for each group
        for key, alert_group in grouped.items():
            title = self.create_issue_title_for_secret_scanning(key, alert_group)
            body = self.create_issue_body_for_secret_scanning(alert_group)

            # Secret scanning alerts are always high priority
            labels = ["security", "secret-scanning", "priority: critical"]

            # Create the issue
            self.create_github_issue(
                title,
                body,
                labels,
                dedupe_key=self._dedupe_key_for_secret_scanning(alert_group),
            )

    def process_dependabot_alerts(self, alerts: List[Dict]) -> None:
        """Process Dependabot vulnerability alerts and create issues."""
        if not alerts:
            self.log("INFO", "No Dependabot alerts to process")
            return

        self.log("INFO", "Processing Dependabot alerts...")
        grouped = self.group_dependabot_alerts(alerts)

        for ghsa_id, alert_group in grouped.items():
            vuln = alert_group[0].get("securityVulnerability") or {}
            advisory = alert_group[0].get("securityAdvisory") or {}
            severity = (vuln.get("severity") or advisory.get("severity") or "").lower()
            severity = severity.replace("moderate", "medium")
            if not self._passes_min_security_severity_level(severity):
                continue

            title = self.create_issue_title_for_dependabot(ghsa_id, alert_group)
            body = self.create_issue_body_for_dependabot(alert_group)

            labels = ["security", "dependabot"]
            if severity in {"critical", "high"}:
                labels.append("priority: high")
            elif severity == "medium":
                labels.append("priority: medium")
            else:
                labels.append("priority: low")

            self.create_github_issue(
                title,
                body,
                labels,
                dedupe_key=self._dedupe_key_for_dependabot(alert_group),
            )

    def generate_summary(self):
        """Generate and print a summary of the execution."""
        print("\n" + "=" * 70)
        print("SUMMARY: Create Issues from Security Alerts")
        print("=" * 70)
        print(f"Repository: {self.owner}/{self.repo}")
        print(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print()
        print("Statistics:")
        print(f"  Code Scanning Alerts Found: {self.stats['code_scanning_alerts']}")
        # Do not log the exact number of secret scanning alerts to avoid exposing
        # potentially sensitive information in clear text logs.
        print("  Secret Scanning Alerts Found: (redacted)")
        print(f"  Dependabot Alerts Found: {self.stats['dependabot_alerts']}")
        print(f"  Issues Created: {self.stats['issues_created']}")
        print(
            f"  Issues Skipped (already exist): {self.stats['issues_skipped_existing']}"
        )
        print("=" * 70)

    def run(self):
        """Run the issue creation workflow."""
        self.log(
            "START", f"Creating issues for security alerts in {self.owner}/{self.repo}"
        )

        if self.dry_run:
            self.log("INFO", "Running in DRY RUN mode - no issues will be created")

        # Fetch alerts
        code_alerts = self.fetch_code_scanning_alerts()
        secret_alerts = self.fetch_secret_scanning_alerts()
        dependabot_alerts = (
            self.fetch_dependabot_alerts() if self.include_dependabot else []
        )

        # Process alerts and create issues
        self.process_code_scanning_alerts(code_alerts)
        self.process_secret_scanning_alerts(secret_alerts)
        self.process_dependabot_alerts(dependabot_alerts)

        # Print summary
        self.generate_summary()


def main():
    parser = argparse.ArgumentParser(
        description="Create GitHub issues from code scanning, secret scanning, and Dependabot alerts",
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
        help="Run in dry-run mode (no issues will be created)",
    )
    parser.add_argument(
        "--min-security-severity",
        choices=["low", "medium", "high", "critical"],
        help="Only create issues for alerts at or above this security severity level",
    )
    parser.add_argument(
        "--include-dependabot",
        action="store_true",
        help="Also create issues from open Dependabot vulnerability alerts (GraphQL).",
    )

    args = parser.parse_args()

    # Get token from args or environment
    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print(
            "ERROR: GitHub token is required. Provide via --token or GITHUB_TOKEN env var"
        )
        print("Create a token at: https://github.com/settings/tokens/new")
        print(
            "Required scopes: repo (security_events needed for code/secret scanning REST)"
        )
        sys.exit(1)

    # Create and run issue creator
    try:
        creator = IssueCreator(
            args.owner,
            args.repo,
            token,
            args.dry_run,
            min_security_severity=args.min_security_severity,
            include_dependabot=args.include_dependabot,
        )
        creator.run()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
