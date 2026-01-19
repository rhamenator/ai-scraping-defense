# Creating GitHub Issues from Security Alerts

This guide explains how to automatically create GitHub issues from code scanning and secret scanning alerts in your repository.

## Overview

The `create_issues_from_alerts.py` script fetches all open code scanning and secret scanning alerts from your repository and creates well-formatted GitHub issues for each alert or group of similar alerts.

## Features

- ✅ **Automatic Grouping**: Groups similar alerts together to avoid creating duplicate issues
- ✅ **Detailed Issues**: Creates comprehensive issues with:
  - Clear titles indicating the security problem
  - Detailed descriptions with affected file locations
  - Remediation guidance and next steps
  - Proper labels and priority tags
- ✅ **Duplicate Detection**: Checks for existing issues before creating new ones
- ✅ **Safe by Default**: Dry-run mode to preview what would be created
- ✅ **Both Alert Types**: Handles both code scanning and secret scanning alerts

## Quick Start

### Prerequisites

1. **Python 3.11+** installed
2. **GitHub Personal Access Token** with scopes:
   - `repo` - Full repository access
   - `security_events` - Read security events

### Create a GitHub Token

1. Go to https://github.com/settings/tokens/new
2. Give it a descriptive name (e.g., "Security Alert Issue Creator")
3. Select scopes:
   - ✅ `repo` (Full control of private repositories)
   - ✅ `security_events` (Read and write security events)
4. Click "Generate token"
5. Copy the token immediately (you won't see it again!)

### Install Dependencies

```bash
pip install requests PyGithub
```

### Set Your Token

```bash
export GITHUB_TOKEN="your_token_here"
```

### Run the Script

#### Option 1: Using the Helper Script (Recommended)

```bash
# Dry-run mode (preview only, no issues created)
./scripts/run_create_issues.sh

# Live mode (actually create issues)
./scripts/run_create_issues.sh --live
```

#### Option 2: Direct Python

```bash
# Dry-run mode
python scripts/create_issues_from_alerts.py \
  --owner rhamenator \
  --repo ai-scraping-defense \
  --dry-run

# Live mode
python scripts/create_issues_from_alerts.py \
  --owner rhamenator \
  --repo ai-scraping-defense
```

#### Option 3: GitHub Actions

1. Go to the **Actions** tab in your repository
2. Select **"Create Issues from Security Alerts"**
3. Click **"Run workflow"**
4. Choose whether to run in dry-run mode
5. Click **"Run workflow"**

The workflow also runs automatically every Monday at 9 AM UTC.

## How It Works

### Code Scanning Alerts

1. **Fetch** all open code scanning alerts from the repository
2. **Group** alerts by:
   - Tool name (e.g., CodeQL, Bandit)
   - Rule ID (e.g., B104, CWE-79)
   - Severity level
3. **Create** one issue per group with:
   - Title: `[Security] ToolName: RuleName - X occurrences (SEVERITY)`
   - Body containing:
     - Rule description
     - List of affected file locations (up to 20)
     - Remediation guidance
     - Links to the original alerts
   - Labels: `security`, `code-scanning`, priority based on severity

### Secret Scanning Alerts

1. **Fetch** all open secret scanning alerts
2. **Group** by secret type (e.g., GitHub Personal Access Token, AWS Access Key)
3. **Create** critical priority issues with:
   - Title: `[Secret] X exposed SecretType detected`
   - Body containing:
     - ⚠️ Critical warning banner
     - List of affected locations
     - Immediate action steps (REVOKE, ROTATE, AUDIT)
     - Detailed remediation steps
     - Prevention best practices
   - Labels: `security`, `secret-scanning`, `priority: critical`

## Example Output

```
[10:30:15] INFO: Fetching code scanning alerts...
[10:30:16] INFO: Found 15 open code scanning alerts
[10:30:16] INFO: Fetching secret scanning alerts...
[10:30:17] INFO: Found 2 open secret scanning alerts
[10:30:17] INFO: Processing 15 code scanning alerts...
[10:30:17] INFO: Grouped into 6 unique alert types
[10:30:18] SUCCESS: Created issue #123: [Security] Bandit: hardcoded_bind_all_interfaces - 2 occurrences (MEDIUM)
[10:30:19] SUCCESS: Created issue #124: [Security] Bandit: try_except_pass - 7 occurrences (LOW)
[10:30:20] SKIP: Issue already exists: #120 - [Security] CodeQL: SQL Injection
...

======================================================================
SUMMARY: Create Issues from Security Alerts
======================================================================
Repository: rhamenator/ai-scraping-defense
Mode: DRY RUN
Timestamp: 2026-01-19T10:30:20.123456

Statistics:
  Code Scanning Alerts Found: 15
  Secret Scanning Alerts Found: 2
  Issues Created: 7
  Issues Skipped (already exist): 1
======================================================================
```

## Issue Format Examples

### Code Scanning Issue Example

**Title:** `[Security] Bandit: hardcoded_bind_all_interfaces - 2 occurrences (MEDIUM)`

**Body:**
```markdown
## Security Alert: hardcoded_bind_all_interfaces

**Rule ID:** `B104`  
**Severity:** MEDIUM  
**Security Severity:** 5.3  

### Description
Possible binding to all interfaces.

### Affected Locations
This alert was found in 2 location(s):

1. [`src/iis_gateway/main.py:184`](https://github.com/.../alert/1) - Alert #42
2. [`src/util/suricata_manager.py:40`](https://github.com/.../alert/2) - Alert #43

### Guidance
Binding to 0.0.0.0 exposes the service to all network interfaces...

### Next Steps
1. Review the affected code locations
2. Understand the security implications
3. Apply appropriate fixes based on the guidance
...
```

**Labels:** `security`, `code-scanning`, `priority: medium`

### Secret Scanning Issue Example

**Title:** `[Secret] 2 exposed GitHub Personal Access Token detected`

**Body:**
```markdown
## Secret Scanning Alert: GitHub Personal Access Token

**Secret Type:** `github_personal_access_token`  
**Number of Locations:** 2

### ⚠️ CRITICAL: Immediate Action Required

Secret scanning has detected exposed credentials in this repository...

### Affected Locations
1. [`config/secrets.yaml:15`](https://github.com/.../alert/5) - Alert #5
2. [`.env.example:23`](https://github.com/.../alert/6) - Alert #6

### Immediate Actions Required
1. **REVOKE** the exposed credentials immediately
2. **ROTATE** to new credentials with proper security
...
```

**Labels:** `security`, `secret-scanning`, `priority: critical`

## Duplicate Prevention

The script implements several strategies to avoid creating duplicate issues:

1. **Grouping**: Similar alerts are grouped together into a single issue
2. **Title Matching**: Before creating an issue, searches for existing issues with similar titles
3. **Skip Existing**: If a matching issue is found, skips creation and logs it

## Best Practices

### When to Run

- **After Security Scans**: Run after CodeQL, Bandit, or other scanning tools complete
- **Weekly**: Use the automated workflow to run weekly and catch new alerts
- **Before Releases**: Run before major releases to ensure all security issues are tracked
- **After Bulk Changes**: Run after refactoring or major code changes

### Workflow

1. **Start with Dry-Run**: Always run in dry-run mode first to see what would be created
2. **Review the Output**: Check that the issues make sense and aren't duplicates
3. **Run Live**: If everything looks good, run in live mode to create the issues
4. **Triage Issues**: Review and prioritize the created issues
5. **Assign Work**: Assign issues to team members
6. **Track Progress**: Close issues as alerts are fixed

### Managing Labels

The script automatically assigns these labels:

- `security` - All security-related issues
- `code-scanning` - Issues from code scanning alerts
- `secret-scanning` - Issues from secret scanning alerts
- `priority: critical` - Secret scanning alerts (always critical)
- `priority: high` - Code scanning alerts with ERROR/CRITICAL severity
- `priority: medium` - Code scanning alerts with WARNING/HIGH severity
- `priority: low` - Code scanning alerts with other severities

You can add these labels to your repository ahead of time for better organization.

## Troubleshooting

### "403 Forbidden" Errors

**Problem**: Cannot access security alerts

**Solutions**:
- Verify your token has `security_events` scope
- Check that code/secret scanning is enabled in repository settings
- For organizations, verify you have proper organization permissions
- Create a new token with correct scopes

### "No alerts found"

**Problem**: Script reports 0 alerts but you know there are alerts

**Solutions**:
- Check that alerts are in "open" state (not dismissed/resolved)
- Verify code/secret scanning is enabled
- Run a security scan first (CodeQL, Bandit, etc.)
- Check repository security tab to confirm alerts exist

### "Issues skipped (already exist)"

**Problem**: All issues are skipped, none created

**Solutions**:
- This is normal if issues already exist for the alerts
- Check your repository's Issues tab
- If issues were closed, reopen them
- If you want to recreate, close/delete existing issues first

### "Import Error: No module named 'requests'"

**Problem**: Required Python packages not installed

**Solution**:
```bash
pip install requests PyGithub
```

## Automation

### GitHub Actions Schedule

The workflow runs automatically every Monday at 9 AM UTC in **live mode**. You can:

- **Disable**: Comment out or remove the `schedule` trigger in the workflow file
- **Change Schedule**: Modify the cron expression (e.g., `0 9 * * 1` = Monday 9 AM)
- **Change Mode**: Edit the workflow to use dry-run for scheduled runs

### Integration with Other Workflows

You can trigger this workflow from other workflows:

```yaml
- name: Create issues from alerts
  uses: ./.github/workflows/create-issues-from-alerts.yml
  with:
    dry_run: false
```

Or call it after security scans:

```yaml
jobs:
  security-scan:
    runs-on: ubuntu-latest
    steps:
      - name: Run CodeQL
        # ... CodeQL scan steps ...
      
      - name: Create issues from alerts
        if: success()
        run: |
          python scripts/create_issues_from_alerts.py \
            --owner ${{ github.repository_owner }} \
            --repo ${{ github.event.repository.name }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Security Considerations

### Token Storage

- ✅ **DO**: Use environment variables (`export GITHUB_TOKEN=...`)
- ✅ **DO**: Use GitHub Secrets for workflows
- ❌ **DON'T**: Hardcode tokens in scripts or commit them
- ❌ **DON'T**: Share tokens or commit them to version control

### Token Scope

Use the minimum required scopes:
- `repo` - Needed to create issues and read repository data
- `security_events` - Needed to read security alerts

Avoid using tokens with broader scopes like `admin:org` unless necessary.

### Token Rotation

- Rotate tokens regularly (every 90 days recommended)
- Revoke tokens that are no longer needed
- Create separate tokens for different purposes

## Advanced Usage

### Custom Filtering

Modify the script to filter specific alert types:

```python
# Only process high severity alerts
if first_alert.get("rule", {}).get("severity", "").lower() not in ["high", "critical"]:
    continue
```

### Custom Labels

Add custom labels based on your workflow:

```python
labels = ["security", "code-scanning"]

# Add team-specific labels
if "auth" in title.lower():
    labels.append("team: security")
elif "api" in title.lower():
    labels.append("team: backend")
```

### Custom Issue Templates

Modify the `create_issue_body_*` functions to match your team's preferred format.

## Getting Help

If you encounter issues:

1. **Check Logs**: Review the script output for specific error messages
2. **Verify Prerequisites**: Ensure Python, packages, and token are set up correctly
3. **Test Token**: Use `gh auth status` to verify your token works
4. **Dry-Run**: Always test with `--dry-run` first
5. **Open an Issue**: If problems persist, open an issue in this repository with:
   - Full error message
   - Steps to reproduce
   - Your environment (Python version, OS, etc.)

## Related Documentation

- [GitHub Code Scanning](https://docs.github.com/en/code-security/code-scanning)
- [GitHub Secret Scanning](https://docs.github.com/en/code-security/secret-scanning)
- [GitHub REST API - Code Scanning](https://docs.github.com/en/rest/code-scanning)
- [GitHub REST API - Secret Scanning](https://docs.github.com/en/rest/secret-scanning)
