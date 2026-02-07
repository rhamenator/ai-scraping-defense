# Quick Start: Alert Management Script

## TL;DR - Get Started in 2 Minutes

```bash
# 1. Install dependencies
pip install requests PyGithub

# 2. Set your GitHub token
export GITHUB_TOKEN="your_github_personal_access_token"

# 3. Run dry-run (no changes made)
python scripts/manage_alerts_issues_prs.py \
  --owner rhamenator \
  --repo ai-scraping-defense \
  --dry-run

# 4. Review the output and report file

# 5. If satisfied, run live mode
python scripts/manage_alerts_issues_prs.py \
  --owner rhamenator \
  --repo ai-scraping-defense
```

## What You Need

1. **Python 3.7+** (check with `python --version`)
2. **GitHub Personal Access Token** with these scopes:
   - `repo`
   - `security_events`
   - `admin:org` (for org-level secret scanning)

## Create GitHub Token

1. Go to: https://github.com/settings/tokens/new
2. Check these boxes:
   - ☑ repo
   - ☑ security_events
   - ☑ admin:org
3. Click "Generate token"
4. Copy the token (you won't see it again!)

## What the Script Does

✅ **Finds duplicate security alerts** and consolidates them
✅ **Finds duplicate issues** and closes them with superseding notes
✅ **Finds duplicate PRs** and closes them with superseding notes
✅ **Diagnoses error-state alerts** and suggests fixes
✅ **Generates detailed report** of all actions

## Output Example

```
[2025-11-22T20:51:28] ANALYSIS: Found 3 groups of duplicate code_scanning alerts
[2025-11-22T20:51:29] CONSOLIDATE: Consolidating code_scanning alert group: codacy:B104:MEDIUM
[2025-11-22T20:51:29] DETAIL:   Primary: #42
[2025-11-22T20:51:29] DETAIL:   Affected files: src/file1.py, src/file2.py
[2025-11-22T20:51:29] DETAIL:   Closing duplicate: #43

STATISTICS:
  Alerts Fetched: 45
  Alerts Consolidated: 12
  Issues Closed: 8
  PRs Closed: 3
```

## Safety Features

- **Dry-run mode**: Test without making changes
- **Detailed logging**: See exactly what will happen
- **Report generation**: Review actions after completion
- **Similarity threshold**: Only consolidates items >80% similar
- **Superseding notes**: All closed items reference the primary item

## Common Issues

**"403 Forbidden"**
→ Your token needs the `security_events` scope

**"Module not found"**
→ Run: `pip install requests PyGithub`

**"404 Not Found"**
→ Feature not enabled (informational, not an error)

## Full Documentation

For detailed information, see: `scripts/ALERT_MANAGEMENT_README.md`

## Need Help?

Open an issue with:
- The error message
- The report file (`alert_management_report_*.txt`)
- Whether you're running in dry-run or live mode
