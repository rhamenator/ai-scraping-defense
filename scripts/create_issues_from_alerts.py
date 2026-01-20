#!/usr/bin/env python3
"""
Create GitHub Issues from Code Scanning and Secret Scanning Alerts

This script fetches all open code scanning and secret scanning alerts from a GitHub
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

try:
    import requests
    from github import Github
except ImportError:
    print("ERROR: Required libraries not installed.")
    print("Please run: pip install requests PyGithub")
    sys.exit(1)

# Configuration constants
SIGNATURE_SEARCH_WORDS = 3  # Number of words from signature to use in search query


class IssueCreator:
    """Creates GitHub issues from security scanning alerts."""

    def __init__(self, owner: str, repo: str, token: str, dry_run: bool = False):
        self.owner = owner
        self.repo = repo
        self.dry_run = dry_run
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
        
        # Track statistics
        self.stats = {
            "code_scanning_alerts": 0,
            "secret_scanning_alerts": 0,
            "issues_created": 0,
            "issues_skipped_existing": 0,
        }

    def log(self, level: str, message: str):
        """Log a message with timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

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
            self.log("INFO", f"Found {len(alerts)} open code scanning alerts")
            return alerts
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                self.log("WARNING", "Code scanning alerts not accessible (403 Forbidden)")
                self.log("INFO", "This may be due to: permissions, feature not enabled, or organization settings")
            elif e.response.status_code == 404:
                self.log("INFO", "Code scanning not enabled for this repository")
            else:
                self.log("ERROR", f"Failed to fetch code scanning alerts: {e}")
            return []
        except Exception as e:
            self.log("ERROR", f"Error fetching code scanning alerts: {e}")
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
            self.log("INFO", f"Found {len(alerts)} open secret scanning alerts")
            return alerts
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                self.log("WARNING", "Secret scanning alerts not accessible (403 Forbidden)")
                self.log("INFO", "This may be due to: permissions, feature not enabled, or organization settings")
            elif e.response.status_code == 404:
                self.log("INFO", "Secret scanning not enabled for this repository")
            else:
                self.log("ERROR", f"Failed to fetch secret scanning alerts: {e}")
            return []
        except Exception as e:
            self.log("ERROR", f"Error fetching secret scanning alerts: {e}")
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

    def create_issue_title_for_code_scanning(self, key: str, alerts: List[Dict]) -> str:
        """Generate issue title for code scanning alert group."""
        first_alert = alerts[0]
        rule = first_alert.get("rule", {})
        rule_id = rule.get("id", "unknown")
        rule_name = rule.get("name", rule_id)
        severity = rule.get("severity", "unknown").upper()
        tool_name = first_alert.get("tool", {}).get("name", "CodeQL")
        
        if len(alerts) == 1:
            return f"[Security] {tool_name}: {rule_name} ({severity})"
        else:
            return f"[Security] {tool_name}: {rule_name} - {len(alerts)} occurrences ({severity})"

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
        
        # Build the issue body
        body = f"""## Security Alert: {rule_name}

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
                line_ref = f":{start_line}" if start_line == end_line else f":{start_line}-{end_line}"
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

    def create_issue_title_for_secret_scanning(self, key: str, alerts: List[Dict]) -> str:
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
        
        body = f"""## Secret Scanning Alert: {secret_type_display}

**Secret Type:** `{secret_type}`  
**Number of Locations:** {len(alerts)}

### ⚠️ CRITICAL: Immediate Action Required

Secret scanning has detected exposed credentials in this repository. This is a critical security issue that must be addressed immediately.

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
                body += f"{i}. [`{path}{line_ref}`]({alert_url}) - Alert #{alert_num}\n"
        
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

### References
- [GitHub Secret Scanning Documentation](https://docs.github.com/en/code-security/secret-scanning)
- [Removing Sensitive Data from a Repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)
"""
        
        return body

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
        signature = re.sub(r'-\s*\d+\s+occurrence[s]?', '', signature)
        signature = re.sub(r'\(\s*(HIGH|MEDIUM|LOW|CRITICAL)\s*\)', '', signature, flags=re.IGNORECASE)
        
        # Clean up and return
        return signature.strip()

    def check_existing_issue(self, title: str) -> Optional[object]:
        """
        Check if an issue with similar title already exists.
        
        Uses a signature-based approach to detect duplicates even when
        titles have different formatting or counts.
        """
        try:
            # Extract signature for this title
            signature = self.extract_issue_signature(title)
            
            # Search for open issues with any part of the signature
            # Use the first significant words from the signature
            search_terms = " ".join(signature.split()[:SIGNATURE_SEARCH_WORDS])
            query = f"repo:{self.owner}/{self.repo} is:issue is:open {search_terms} in:title"
            results = self.gh.search_issues(query)
            
            for issue in results:
                # Extract signature from existing issue
                existing_signature = self.extract_issue_signature(issue.title)
                
                # Check if signatures match closely
                if signature.lower() == existing_signature.lower():
                    return issue
            
            return None
        except Exception as e:
            self.log("WARNING", f"Error checking for existing issue: {e}")
            return None

    def create_github_issue(self, title: str, body: str, labels: List[str]) -> bool:
        """Create a GitHub issue."""
        try:
            # Check if similar issue already exists
            existing = self.check_existing_issue(title)
            if existing:
                self.log("SKIP", f"Issue already exists: #{existing.number} - {existing.title}")
                self.stats["issues_skipped_existing"] += 1
                return False
            
            if self.dry_run:
                # Avoid logging potentially sensitive issue titles in clear text
                self.log("DRY-RUN", "Would create issue (title redacted)")
                self.log("DRY-RUN", f"  Labels: {', '.join(labels)}")
                self.stats["issues_created"] += 1
                return True
            
            # Create the issue
            issue = self.repository.create_issue(
                title=title,
                body=body,
                labels=labels
            )
            
            self.log("SUCCESS", f"Created issue #{issue.number}: {title}")
            self.stats["issues_created"] += 1
            return True
            
        except Exception as e:
            self.log("ERROR", f"Failed to create issue '{title}': {e}")
            return False

    def process_code_scanning_alerts(self, alerts: List[Dict]):
        """Process code scanning alerts and create issues."""
        if not alerts:
            self.log("INFO", "No code scanning alerts to process")
            return
        
        self.log("INFO", f"Processing {len(alerts)} code scanning alerts...")
        
        # Group alerts
        grouped = self.group_code_scanning_alerts(alerts)
        self.log("INFO", f"Grouped into {len(grouped)} unique alert types")
        
        # Create issues for each group
        for key, alert_group in grouped.items():
            title = self.create_issue_title_for_code_scanning(key, alert_group)
            body = self.create_issue_body_for_code_scanning(alert_group)
            
            # Determine labels
            first_alert = alert_group[0]
            severity = first_alert.get("rule", {}).get("severity", "").lower()
            
            labels = ["security", "code-scanning"]
            
            if severity == "error" or severity == "critical":
                labels.append("priority: high")
            elif severity == "warning" or severity == "high":
                labels.append("priority: medium")
            else:
                labels.append("priority: low")
            
            # Create the issue
            self.create_github_issue(title, body, labels)

    def process_secret_scanning_alerts(self, alerts: List[Dict]):
        """Process secret scanning alerts and create issues."""
        if not alerts:
            self.log("INFO", "No secret scanning alerts to process")
            return
        
        self.log("INFO", f"Processing {len(alerts)} secret scanning alerts...")
        
        # Group alerts
        grouped = self.group_secret_scanning_alerts(alerts)
        self.log("INFO", f"Grouped into {len(grouped)} unique secret types")
        
        # Create issues for each group
        for key, alert_group in grouped.items():
            title = self.create_issue_title_for_secret_scanning(key, alert_group)
            body = self.create_issue_body_for_secret_scanning(alert_group)
            
            # Secret scanning alerts are always high priority
            labels = ["security", "secret-scanning", "priority: critical"]
            
            # Create the issue
            self.create_github_issue(title, body, labels)

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
        print(f"  Issues Created: {self.stats['issues_created']}")
        print(f"  Issues Skipped (already exist): {self.stats['issues_skipped_existing']}")
        print("=" * 70)

    def run(self):
        """Run the issue creation workflow."""
        self.log("START", f"Creating issues for security alerts in {self.owner}/{self.repo}")
        
        if self.dry_run:
            self.log("INFO", "Running in DRY RUN mode - no issues will be created")
        
        # Fetch alerts
        code_alerts = self.fetch_code_scanning_alerts()
        secret_alerts = self.fetch_secret_scanning_alerts()
        
        # Process alerts and create issues
        self.process_code_scanning_alerts(code_alerts)
        self.process_secret_scanning_alerts(secret_alerts)
        
        # Print summary
        self.generate_summary()


def main():
    parser = argparse.ArgumentParser(
        description="Create GitHub issues from code scanning and secret scanning alerts",
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

    args = parser.parse_args()

    # Get token from args or environment
    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: GitHub token is required. Provide via --token or GITHUB_TOKEN env var")
        print("Create a token at: https://github.com/settings/tokens/new")
        print("Required scopes: repo, security_events")
        sys.exit(1)

    # Create and run issue creator
    try:
        creator = IssueCreator(args.owner, args.repo, token, args.dry_run)
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
