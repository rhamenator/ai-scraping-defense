# Alert, Issue, and PR Management Guide

## Overview

This guide explains how to manage security alerts, issues, and pull requests in the AI Scraping Defense repository. The management system helps you:

- **Consolidate duplicates** - Identify and merge duplicate alerts, issues, and PRs
- **Diagnose errors** - Find and fix alerts with error states
- **Maintain clarity** - Keep your repository organized and focused
- **Track progress** - Generate comprehensive reports of management actions

## Understanding the Problem

As repositories grow, you may encounter:

1. **Duplicate Alerts** - Same security issue detected in multiple files
2. **Duplicate Issues** - Similar issues created multiple times
3. **Duplicate PRs** - Multiple PRs addressing the same problem
4. **Error-State Alerts** - Alerts that failed to complete properly
5. **Stale Alerts** - Outdated alerts that need review

## Solution: Automated Management Script

The `manage_alerts_issues_prs.py` script automates the management process.

### What Makes an Item a "Duplicate"?

The script considers items duplicates when they:

- Have **similar titles** (after normalizing common prefixes)
- Have **similar content** (>80% similarity threshold)
- Represent the **same underlying issue** (not just same file path)

**Important**: The script does NOT consider these as reasons for duplication:
- Different file paths
- Different line numbers
- Different IDs or timestamps
- Different assignees or labels

### Consolidation Process

When duplicates are found:

1. **Identify Primary** - The oldest item (lowest number) becomes primary
2. **Collect Information** - All affected files/locations are noted
3. **Close Duplicates** - Secondary items are closed with references
4. **Add Notes** - Closure comment explains superseding relationship

Example closure note:
```
Closing as duplicate. This issue is superseded by #123 which consolidates
all related concerns across the following files: file1.py, file2.py, file3.py
```

## Quick Start

### Prerequisites

1. **Python 3.7+**
2. **GitHub Personal Access Token** with:
   - `repo` scope
   - `security_events` scope
   - `admin:org` scope (for org-level features)

### Installation

```bash
# Install required libraries
pip install requests PyGithub

# Set your GitHub token
export GITHUB_TOKEN="your_github_personal_access_token"
```

### Running the Script

#### Dry Run (Recommended First)

```bash
python scripts/manage_alerts_issues_prs.py \
  --owner rhamenator \
  --repo ai-scraping-defense \
  --dry-run
```

This will:
- Show you what would happen
- Generate a report
- Make NO actual changes

#### Live Run

After reviewing the dry-run output:

```bash
python scripts/manage_alerts_issues_prs.py \
  --owner rhamenator \
  --repo ai-scraping-defense
```

This will:
- Make actual changes
- Close duplicate items
- Generate a final report

## What Gets Managed

### 1. Security Alerts

#### Code Scanning Alerts
- Groups by: tool name, rule ID, severity, description
- Consolidates: alerts differing only in file paths
- Closes: duplicate alerts with `dismissed` state
- Note: References primary alert and lists all affected files

#### Secret Scanning Alerts
- Groups by: secret type, pattern
- Consolidates: alerts differing only in file locations
- Closes: duplicate alerts with `resolved` state
- Note: References primary alert and lists all locations

#### Dependabot Alerts
- Groups by: package name, vulnerability ID
- Consolidates: alerts differing only in dependency files
- Closes: duplicate alerts with `dismissed` state
- Note: References primary alert and lists all dependencies

### 2. Issues

- Groups by: normalized title and body content similarity
- Consolidates: issues >80% similar in content
- Closes: duplicate issues with `not_planned` state
- Note: References primary issue that consolidates concerns

### 3. Pull Requests

- Groups by: normalized title and body content similarity
- Consolidates: PRs >80% similar in content
- Closes: duplicate PRs
- Note: References primary PR with consolidated changes

## Error Diagnosis

The script identifies and diagnoses alerts with error states:

| Error Reason | Diagnosis | Suggested Fix |
|--------------|-----------|---------------|
| `stale` | Alert outdated | Re-run scan or verify if issue exists |
| `timeout` | Scan timeout | Optimize codebase or increase timeout |
| `analysis_error` | Analysis failed | Check logs and re-run scan |
| `insufficient_permissions` | Scanner lacks permissions | Review and grant necessary permissions |
| `configuration_error` | Configuration issue | Review scanner configuration |

## Output and Reports

### Console Output

Real-time logging shows:
```
[2025-11-22T20:51:28] FETCH: Fetching code scanning alerts...
[2025-11-22T20:51:29] INFO: Fetched 15 code scanning alerts
[2025-11-22T20:51:30] ANALYSIS: Found 3 groups of duplicate alerts
[2025-11-22T20:51:31] CONSOLIDATE: Consolidating alert group...
```

### Report File

Generated as `alert_management_report_YYYYMMDD_HHMMSS.txt`:

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
  Alerts Consolidated: 12
  Issues Closed: 8
  PRs Closed: 3
  Errors Diagnosed: 2

ACTIONS LOG:
--------------------------------------------------------------------------------
[timestamp] action: details
...
```

## Best Practices

### 1. Start with Dry Run

Always run in dry-run mode first to:
- Preview what will happen
- Verify the grouping is correct
- Check that the right items will be consolidated

### 2. Review Consolidation Groups

Check the console output to see:
- Which items are grouped together
- Why they are considered duplicates
- What the primary item will be

### 3. Run Regularly

Schedule the script to run:
- **Weekly** - For active repositories
- **After scans** - When security scans complete
- **Before releases** - As part of release prep
- **On demand** - When you notice duplicates accumulating

### 4. Monitor Permissions

If you see permission errors:
- Verify your GitHub token has the required scopes
- Check that security features are enabled
- Ensure you have admin access to the repository

### 5. Review Reports

After each run:
- Check the statistics
- Review the actions log
- Verify closed items reference the correct primary item
- Ensure no unexpected consolidations occurred

## Advanced Usage

### Custom Similarity Threshold

To adjust duplicate detection sensitivity, modify the script:

```python
# Around line 445 in manage_alerts_issues_prs.py
if similarity > 0.8:  # Change threshold (0.0 to 1.0)
    # 0.6 = more aggressive (finds more duplicates)
    # 0.9 = more conservative (finds fewer duplicates)
```

### Filter by Label

To only process items with specific labels:

```python
# After line 441 in manage_alerts_issues_prs.py
issues = [i for i in issues if "security" in [l.name for l in i.labels]]
```

### GitHub Actions Integration

Run automatically via workflow:

```yaml
# .github/workflows/manage-alerts.yml
name: Manage Alerts
on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly
  workflow_dispatch:     # Manual trigger

jobs:
  manage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install deps
        run: pip install requests PyGithub
      - name: Run script
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python scripts/manage_alerts_issues_prs.py \
            --owner ${{ github.repository_owner }} \
            --repo ${{ github.event.repository.name }} \
            --dry-run
```

## Troubleshooting

### Permission Errors (403)

**Symptom**: `403 Forbidden: Insufficient permissions`

**Solution**:
1. Check your token has `security_events` scope
2. Verify you're an admin or owner of the repository
3. For org repos, check org-level security settings

### Not Found Errors (404)

**Symptom**: `404 Not Found` when fetching alerts

**Solution**: This is informational, not an error. It means:
- Code scanning not enabled → Enable in repository settings
- Secret scanning not enabled → Enable in repository settings
- Dependabot not enabled → Enable in repository settings

### Module Not Found

**Symptom**: `ModuleNotFoundError: No module named 'github'`

**Solution**:
```bash
pip install requests PyGithub
```

### Rate Limiting

**Symptom**: `API rate limit exceeded`

**Solution**:
- Wait for rate limit reset (check response headers)
- Use a token with higher rate limits
- Reduce script execution frequency
- For GitHub Actions, use `GITHUB_TOKEN` which has higher limits

### Unexpected Consolidations

**Symptom**: Items consolidated that shouldn't be

**Solution**:
1. Review the similarity threshold (default 0.8)
2. Check if titles are too similar after normalization
3. Adjust the threshold or title normalization logic
4. Run in dry-run mode to preview changes

## FAQs

**Q: Will this delete my alerts/issues/PRs?**
A: No. It closes them with appropriate states and adds references to the primary item.

**Q: Can I undo the changes?**
A: Yes. Closed items can be reopened manually. Comments explaining consolidation remain.

**Q: How often should I run this?**
A: Weekly for active repos, or after security scans. Start with dry-run monthly.

**Q: What if I disagree with a consolidation?**
A: Reopen the closed item and it won't be re-consolidated unless it matches again.

**Q: Does this work with private repositories?**
A: Yes, with a token that has access to private repos (`repo` scope).

**Q: Can this run in CI/CD?**
A: Yes! See the GitHub Actions integration section above.

## Support

For issues or questions:

1. **Check this guide** - Most common issues are covered
2. **Review script output** - Error messages are descriptive
3. **Check report file** - Shows what happened and why
4. **Open an issue** - Include:
   - Error message
   - Report file
   - Dry-run or live mode
   - What you expected vs. what happened

## Related Documentation

- `QUICK_START_ALERT_MANAGEMENT.md` - Quick start guide
- `scripts/ALERT_MANAGEMENT_README.md` - Detailed technical documentation
- `scripts/manage_alerts_issues_prs.py` - Script source code (well commented)
- `.github/workflows/manage-alerts.yml` - GitHub Actions workflow

## License

This tooling is part of the AI Scraping Defense project and follows the same license.
