# Scripts Directory

## Security Alert Management

### create_issues_from_alerts.py

**Purpose**: Automatically create GitHub issues from code scanning and secret scanning alerts.

**Usage**:
```bash
# Dry-run mode (preview only)
python scripts/create_issues_from_alerts.py --owner OWNER --repo REPO --dry-run

# Live mode (create issues)
python scripts/create_issues_from_alerts.py --owner OWNER --repo REPO

# Using environment variable for token
export GITHUB_TOKEN="your_token"
python scripts/create_issues_from_alerts.py --owner OWNER --repo REPO
```

**Features**:
- Groups similar alerts to avoid duplicate issues
- Creates detailed issues with remediation guidance
- Checks for existing issues before creating new ones
- Supports both code scanning and secret scanning alerts
- Safe dry-run mode

**Requirements**:
- Python 3.11+
- `pip install requests PyGithub`
- GitHub token with `repo` and `security_events` scopes

**See Also**: [Full Documentation](../docs/creating_issues_from_alerts.md)

---

### run_create_issues.sh

**Purpose**: Helper script to run `create_issues_from_alerts.py` with prerequisites checks.

**Usage**:
```bash
# Dry-run mode (default)
./scripts/run_create_issues.sh

# Live mode
./scripts/run_create_issues.sh --live
```

**Features**:
- Checks for Python, pip, and required packages
- Validates GitHub token is set
- Colored output for better readability
- Confirms before creating issues in live mode

---

### manage_alerts_issues_prs.py

**Purpose**: Comprehensive alert, issue, and PR management including consolidation and deduplication.

**Usage**:
```bash
python scripts/manage_alerts_issues_prs.py --owner OWNER --repo REPO --dry-run
```

**Features**:
- Consolidates duplicate alerts
- Merges duplicate issues and PRs
- Diagnoses error-state alerts
- Generates comprehensive reports

**See Also**: [Alert Management Guide](../docs/alert_management_guide.md)

---

### create_code_scanning_issues.py

**Purpose**: Create GitHub issues from Bandit scan results.

**Usage**:
```bash
# First run Bandit to generate results
bandit -r src/ -f json -o /tmp/bandit-results.json

# Then create issues
python scripts/create_code_scanning_issues.py
```

**Features**:
- Processes Bandit JSON results
- Groups findings by test ID
- Creates or generates report based on GH_TOKEN availability

---

## Other Scripts

For other scripts in this directory, refer to their individual documentation or inline comments.

## Common Requirements

Most security-related scripts in this directory require:

1. **Python 3.11+**
2. **GitHub Personal Access Token** with appropriate scopes
3. **Python packages**: `requests`, `PyGithub`

Install dependencies:
```bash
pip install -r requirements.txt
```

Set your GitHub token:
```bash
export GITHUB_TOKEN="your_token_here"
```

## Getting Help

- Read the specific script documentation in `docs/`
- Check inline comments in the script files
- Open an issue if you encounter problems
