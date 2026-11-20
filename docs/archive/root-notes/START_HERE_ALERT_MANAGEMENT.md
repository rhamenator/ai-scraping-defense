# 🚀 START HERE: Alert Management System

**Welcome!** This document is your entry point to the Alert Management System. Read this first, then follow the links for more details.

## What Problem Does This Solve?

Your repository has:
- ❌ Duplicate security alerts (same problem, different files)
- ❌ Duplicate issues (same topic, slightly different wording)
- ❌ Duplicate PRs (same fix, multiple attempts)
- ❌ Error-state alerts (failed scans, need diagnosis)
- ❌ Growing clutter that makes real issues hard to find

## What This System Does

✅ **Finds Duplicates** - Smart content-based detection
✅ **Consolidates Items** - Keeps one, closes rest with notes
✅ **Diagnoses Errors** - Identifies issues and suggests fixes
✅ **Generates Reports** - Complete audit trail of actions
✅ **Safe by Default** - Dry-run mode to preview changes

## Quick Start (3 Steps)

### Step 1: Install Requirements (30 seconds)

```bash
pip install requests PyGithub
```

### Step 2: Set Your Token (30 seconds)

Create a GitHub token at: https://github.com/settings/tokens/new

Check these boxes:
- ☑ repo
- ☑ security_events
- ☑ admin:org

Then:
```bash
export GITHUB_TOKEN="your_token_here"
```

### Step 3: Run It! (1 minute)

```bash
./scripts/run_alert_management.sh
```

That's it! The script will:
1. ✓ Check prerequisites
2. ✓ Fetch all alerts, issues, PRs
3. ✓ Identify duplicates
4. ✓ Show you what it would do (DRY RUN - no changes)
5. ✓ Generate a report

Review the output. If you like what you see:

```bash
./scripts/run_alert_management.sh --live
```

## Example Output

```
╔═══════════════════════════════════════════════════════════╗
║   Security Alert, Issue, and PR Management Tool          ║
╚═══════════════════════════════════════════════════════════╝

✓ Python 3 found
✓ Required packages found
✓ GitHub token found

Configuration:
  Repository: rhamenator/ai-scraping-defense
  Mode: DRY RUN (no changes will be made)

Starting alert management...

[20:51:28] FETCH: Fetching code scanning alerts...
[20:51:29] INFO: Fetched 15 alerts
[20:51:30] ANALYSIS: Found 3 groups of duplicates
[20:51:31] CONSOLIDATE: Alert group: codacy:B104:MEDIUM
[20:51:31] DETAIL:   Primary: #42
[20:51:31] DETAIL:   Affected files: src/file1.py, src/file2.py
[20:51:31] DETAIL:   Closing duplicate: #43

STATISTICS:
  Alerts Fetched: 45
  Alerts Consolidated: 12
  Issues Closed: 8
  PRs Closed: 3
  Errors Diagnosed: 2

✓ Report saved to: alert_management_report_20251122_205128.txt
```

## What Makes It Smart?

### Not Just File-Based
❌ **Wrong**: "Same file path = duplicate"
✅ **Right**: "Same problem type + 80% similar content = duplicate"

### Example
These ARE duplicates (will be consolidated):
```
Alert #1: "B104: hardcoded_bind_all_interfaces in src/file1.py"
Alert #2: "B104: hardcoded_bind_all_interfaces in src/file2.py"
```

These are NOT duplicates (will be kept separate):
```
Alert #1: "B104: hardcoded_bind_all_interfaces"
Alert #2: "B110: try_except_pass"
```

## Safety Features

🛡️ **Dry-Run Mode** - Test without making changes
🛡️ **Detailed Logging** - See exactly what will happen
🛡️ **Comprehensive Reports** - Full audit trail
🛡️ **Superseding Notes** - All closures reference primary item
🛡️ **Graceful Errors** - Handles API failures without crashing

## Documentation Map

Start here, then explore based on your needs:

```
START_HERE_ALERT_MANAGEMENT.md (You are here!)
│
├─→ QUICK_START_ALERT_MANAGEMENT.md
│   ↓ 2-minute quick start
│   ↓ Token creation
│   ↓ Common issues
│
├─→ docs/alert_management_guide.md
│   ↓ Complete feature guide
│   ↓ How duplicates are defined
│   ↓ Consolidation process
│   ↓ Error diagnosis
│   ↓ Best practices
│   ↓ Troubleshooting
│   ↓ FAQs
│
├─→ scripts/ALERT_MANAGEMENT_README.md
│   ↓ Technical documentation
│   ↓ API details
│   ↓ Command-line options
│   ↓ CI/CD integration
│   ↓ Advanced customization
│
├─→ docs/alert_management_flow.md
│   ↓ Visual flow diagrams
│   ↓ Architecture overview
│   ↓ Decision trees
│   ↓ Process flows
│
└─→ ALERT_MANAGEMENT_SUMMARY.md
    ↓ Implementation summary
    ↓ Complete feature list
    ↓ Files created
```

## Three Ways to Run

### 1. Helper Script (Easiest)
```bash
./scripts/run_alert_management.sh
```
- ✓ Checks prerequisites
- ✓ Colored output
- ✓ Confirms before changes
- ✓ Best for manual runs

### 2. Direct Python (Most Control)
```bash
python scripts/manage_alerts_issues_prs.py \
  --owner rhamenator \
  --repo ai-scraping-defense \
  --dry-run
```
- ✓ Full control over options
- ✓ Best for scripting
- ✓ Easier to customize

### 3. GitHub Actions (Automated)
Go to Actions tab → "Manage Security Alerts and Issues" → Run workflow
- ✓ Runs automatically (weekly)
- ✓ No local setup needed
- ✓ Report saved as artifact
- ✓ Best for regular maintenance

## What Gets Managed?

### Security Alerts
- **Code Scanning**: Codacy, CodeQL, etc.
- **Secret Scanning**: Tokens, credentials
- **Dependabot**: Vulnerable dependencies

### Issues
- Duplicate detection by title/content
- Consolidation with superseding notes

### Pull Requests
- Duplicate detection by title/content
- Consolidation with references

## Common Questions

### Q: Will this delete my items?
**A:** No! It closes them with proper states and adds notes. You can reopen anything.

### Q: How do I know what will be consolidated?
**A:** Run with `--dry-run` first. It shows everything without making changes.

### Q: What if I disagree with a consolidation?
**A:** Reopen the closed item. It won't be re-closed unless it matches again.

### Q: Is my token safe?
**A:** Yes. It's never logged or displayed. Use environment variable for security.

### Q: How often should I run this?
**A:** Weekly for active repos, or after security scans. Start with monthly dry-runs.

## Next Steps

Choose your path:

### 🎯 Just Want to Try It?
→ Follow the "Quick Start" above (3 steps)

### 📚 Want to Understand It First?
→ Read [docs/alert_management_guide.md](../../alert_management_guide.md)

### 🔧 Want to Customize It?
→ Read [scripts/ALERT_MANAGEMENT_README.md](../../../scripts/ALERT_MANAGEMENT_README.md)

### 🤖 Want to Automate It?
→ Use `.github/workflows/manage-alerts.yml`

### 🐛 Having Problems?
→ Check [QUICK_START_ALERT_MANAGEMENT.md](QUICK_START_ALERT_MANAGEMENT.md) troubleshooting section

## Need Help?

1. **Check the docs** - Most questions are answered
2. **Review error messages** - They're descriptive
3. **Check the report file** - Shows what happened
4. **Open an issue** - Include:
   - Error message
   - Report file
   - Dry-run or live mode
   - What you expected

## Success Metrics

After running, you'll see:
- ✅ **Fewer duplicate alerts** - Cleaner security tab
- ✅ **Consolidated issues** - Easier to track
- ✅ **Better focus** - Less noise, more signal
- ✅ **Clear audit trail** - Know what was done

## Ready?

Let's get started! Run:

```bash
./scripts/run_alert_management.sh
```

Or if you want to dive deeper first:

```bash
cat QUICK_START_ALERT_MANAGEMENT.md
```

---

**Remember**: Always start with dry-run mode to see what will happen!

Happy managing! 🎉
