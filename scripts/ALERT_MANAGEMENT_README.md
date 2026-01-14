# Security Alert, Issue, and PR Management Guide

This guide explains how to use the `manage_alerts_issues_prs.py` script to manage security alerts, issues, and pull requests in the repository.

## Overview

The script performs the following tasks:

1. **Fetch Security Alerts**: Retrieves all code scanning, secret scanning, and Dependabot alerts
2. **Identify Duplicates**: Groups alerts, issues, and PRs by their essential properties (not by file paths or IDs)
3. **Consolidate Duplicates**: Closes duplicate items and adds notes referencing the primary item
4. **Diagnose Errors**: Identifies alerts with "Error" state and suggests remediation
5. **Generate Report**: Creates a comprehensive report of all actions taken

## Prerequisites

### 1. Install Required Python Packages

```bash
pip install requests PyGithub
```

### 2. Create a GitHub Personal Access Token

You need a GitHub Personal Access Token (PAT) with the following scopes:

- `repo` - Full control of private repositories
- `security_events` - Read and write security events (for code scanning and secret scanning alerts)
- `admin:org` - Read org and team membership (for organization-level secret scanning)

To create a token:

1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Select the scopes listed above
4. Generate and copy the token

## Usage

### Basic Usage

```bash
# Dry run (no changes will be made)
python scripts/manage_alerts_issues_prs.py \
  --owner rhamenator \
  --repo ai-scraping-defense \
  --token YOUR_GITHUB_TOKEN \
  --dry-run

# Live run (will make actual changes)
python scripts/manage_alerts_issues_prs.py \
  --owner rhamenator \
  --repo ai-scraping-defense \
  --token YOUR_GITHUB_TOKEN
```

### Using Environment Variable for Token

```bash
# Set token as environment variable
export GITHUB_TOKEN="your_github_token_here"

# Run script
python scripts/manage_alerts_issues_prs.py \
  --owner rhamenator \
  --repo ai-scraping-defense \
  --dry-run
```

### Command-Line Options

- `--owner`: GitHub repository owner (required)
- `--repo`: GitHub repository name (required)
- `--token`: GitHub Personal Access Token (optional if GITHUB_TOKEN env var is set)
- `--dry-run`: Run in dry-run mode without making any changes (recommended for first run)

## What the Script Does

### 1. Security Alerts Management

#### Code Scanning Alerts
- Fetches all open code scanning alerts
- Groups alerts by tool, rule ID, severity, and description
- Consolidates duplicates that differ only in file paths
- Diagnoses alerts with error states
- Closes duplicate alerts with a reference to the primary alert

#### Secret Scanning Alerts
- Fetches all open secret scanning alerts
- Groups alerts by secret type and pattern
- Consolidates duplicates across different files
- Closes duplicate alerts with resolution comments

#### Dependabot Alerts
- Fetches all open Dependabot alerts
- Groups alerts by package and vulnerability
- Consolidates duplicates across different dependency files
- Dismisses duplicate alerts with appropriate reasons

### 2. Issues Management

- Fetches all open issues (excluding PRs)
- Identifies duplicates based on:
  - Title similarity (after removing common prefixes)
  - Body content similarity (>80% threshold)
- Consolidates duplicates by:
  - Keeping the oldest issue as primary
  - Closing duplicate issues with a comment referencing the primary
  - Marking as "not_planned" to indicate consolidation

### 3. Pull Requests Management

- Fetches all open pull requests
- Identifies duplicates based on:
  - Title similarity (after removing common prefixes like "fix:", "feat:")
  - Body content similarity (>80% threshold)
- Consolidates duplicates by:
  - Keeping the oldest PR as primary
  - Closing duplicate PRs with a comment referencing the primary

### 4. Error Diagnosis

The script diagnoses alerts with error states and suggests remediation:

- **Stale**: Alert may be outdated, re-run scan
- **Timeout**: Scan timeout, optimize codebase or increase timeout
- **Analysis Error**: Analysis failed, check logs and re-run
- **Insufficient Permissions**: Scanner lacks permissions
- **Configuration Error**: Review scanner configuration

## Output

### Console Output

The script provides real-time logging of all actions:

```
[2025-11-22T20:51:28] FETCH: Fetching code scanning alerts...
[2025-11-22T20:51:29] INFO: Fetched 15 code scanning alerts
[2025-11-22T20:51:30] ANALYSIS: Found 3 groups of duplicate code_scanning alerts
[2025-11-22T20:51:31] CONSOLIDATE: Consolidating code_scanning alert group: codacy:B104:MEDIUM:...
...
```

### Report File

A detailed report is saved to a timestamped file (e.g., `alert_management_report_20251122_205128.txt`) containing:

- Repository information
- Execution mode (DRY RUN or LIVE)
- Statistics summary:
  - Alerts fetched
  - Alerts reopened
  - Alerts consolidated/closed
  - Issues created/closed/consolidated
  - PRs closed/consolidated
  - Errors diagnosed
- Complete actions log with timestamps

## Example Report

```
================================================================================
SECURITY ALERT, ISSUE, AND PR MANAGEMENT REPORT
================================================================================
Repository: rhamenator/ai-scraping-defense
Timestamp: 2025-11-22T20:51:28.252Z
Mode: DRY RUN

STATISTICS:
--------------------------------------------------------------------------------
  Alerts Fetched: 45
  Alerts Reopened: 0
  Alerts Consolidated: 12
  Alerts Closed: 12
  Issues Created: 0
  Issues Closed: 8
  Issues Consolidated: 8
  Prs Closed: 3
  Prs Consolidated: 3
  Errors Diagnosed: 2

ACTIONS LOG:
--------------------------------------------------------------------------------
[2025-11-22T20:51:28] START: Starting alert management for rhamenator/ai-scraping-defense
[2025-11-22T20:51:28] INFO: Running in DRY RUN mode - no changes will be made
...
```

## Best Practices

### 1. Always Run Dry-Run First

```bash
python scripts/manage_alerts_issues_prs.py \
  --owner rhamenator \
  --repo ai-scraping-defense \
  --dry-run
```

Review the output and report before running in live mode.

### 2. Review Consolidation Groups

Check the console output to see which items will be consolidated. The script groups items by:
- Essential properties (not file paths or IDs)
- Content similarity (>80% threshold)

### 3. Backup Important Data

Before running in live mode, consider:
- Creating a branch or tag as a restore point
- Exporting issues/PRs if needed
- Taking screenshots of important alerts

### 4. Run Regularly

Consider running this script:
- Weekly to manage growing alerts and issues
- After major security scans
- Before release cycles
- As part of repository maintenance

### 5. Monitor Permissions

If you encounter 403 or 404 errors:
- Verify your GitHub token has the required scopes
- Check that security features are enabled (code scanning, secret scanning, Dependabot)
- Ensure you have admin access to the repository

## Troubleshooting

### Permission Errors (403)

```
ERROR: 403 Forbidden: Insufficient permissions for code scanning alerts
```

**Solution**: Ensure your GitHub token has the `security_events` scope.

### Not Found Errors (404)

```
INFO: Code scanning not enabled for this repository
```

**Solution**: This is informational. Enable the security feature if needed.

### Module Not Found

```
ERROR: Required libraries not installed.
```

**Solution**: Run `pip install requests PyGithub`

### API Rate Limits

If you hit GitHub API rate limits:
- Wait for the rate limit to reset
- Use a token with higher rate limits
- Reduce the frequency of script execution

## Advanced Usage

### Custom Similarity Threshold

To adjust the similarity threshold for duplicate detection, modify the script:

```python
# Line ~445 in manage_alerts_issues_prs.py
if similarity > 0.8:  # Change this threshold
```

### Filtering by Label

To only process issues with specific labels, add filtering:

```python
# After line ~441 in manage_alerts_issues_prs.py
issues = [i for i in issues if "security" in [l.name for l in i.labels]]
```

### Custom Alert Grouping

To customize how alerts are grouped, modify the `normalize_alert_key` method around line ~71.

## Integration with CI/CD

You can integrate this script into your CI/CD pipeline:

```yaml
# .github/workflows/manage-alerts.yml
name: Manage Security Alerts

on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly on Sunday
  workflow_dispatch:

jobs:
  manage-alerts:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: pip install requests PyGithub
      
      - name: Run alert management
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python scripts/manage_alerts_issues_prs.py \
            --owner ${{ github.repository_owner }} \
            --repo ${{ github.event.repository.name }} \
            --dry-run
      
      - name: Upload report
        uses: actions/upload-artifact@v3
        with:
          name: alert-management-report
          path: alert_management_report_*.txt
```

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the script source code comments
3. Open an issue in the repository with the error message and report file

## License

This script is part of the AI Scraping Defense project and follows the same license.
