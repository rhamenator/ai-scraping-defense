# Code Scanning and Issue Creation Process

This document describes the process for running code scanning tools and creating GitHub issues for identified problems.

## Overview

The repository uses multiple code scanning tools to maintain code quality and security:

1. **Flake8** - Python code quality and PEP 8 compliance
2. **Bandit** - Python security vulnerability scanner
3. **Codacy** - Automated code review platform (via GitHub Actions)

## Running Code Scans Locally

### Flake8 (Code Quality)

```bash
# Install flake8
pip install flake8

# Run on entire src directory
flake8 src/ --count --statistics

# Run on specific files
flake8 src/path/to/file.py

# Configuration is in .flake8 file
```

### Bandit (Security)

```bash
# Install bandit
pip install bandit

# Run security scan and output to JSON
bandit -r src/ -f json -o /tmp/bandit-results.json

# Run with severity filter
bandit -r src/ -ll  # Only show medium and high severity
```

### Pre-commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run manually on all files
pre-commit run --all-files

# Run on specific files
pre-commit run --files src/file1.py src/file2.py
```

## Creating GitHub Issues from Scan Results

### Automated Script

We provide a script that automatically creates GitHub issues from code scanning results:

```bash
# Run Bandit scan first
bandit -r src/ -f json -o /tmp/bandit-results.json

# Generate issues (requires GH_TOKEN environment variable)
python3 scripts/create_code_scanning_issues.py

# Or generate a markdown report if GH_TOKEN is not available
python3 scripts/create_code_scanning_issues.py
# This will create CODE_SCANNING_ISSUES.md
```

### Manual Issue Creation

If you prefer to create issues manually:

1. Run the appropriate scanning tool
2. Review the output
3. Create issues using `gh` CLI:

```bash
gh issue create \
  --title "[Code Quality] Issue Title" \
  --body "Description of the issue" \
  --label security,code-quality
```

## Issue Labeling Guidelines

All code scanning issues should use these labels:

- `security` - For security-related findings
- `code-quality` - For code quality issues
- `automated` - For issues created by automated tools
- `priority-high` - For high severity issues
- `priority-medium` - For medium severity issues
- `priority-low` - For low severity issues

## Common Issues and Fixes

### B110: try-except-pass

**Issue**: Silent exception handling without logging or proper error handling.

**Fix**:
```python
# Before
try:
    risky_operation()
except Exception:
    pass

# After
try:
    risky_operation()
except Exception as e:
    logger.warning(f"Operation failed (expected): {e}")
    # Or handle the specific exception type
```

### B104: hardcoded_bind_all_interfaces

**Issue**: Binding to 0.0.0.0 can expose services to unintended networks.

**Fix**:
```python
# Before
app.run(host="0.0.0.0", port=8000)

# After
host = os.environ.get("BIND_HOST", "127.0.0.1")
app.run(host=host, port=8000)
```

### B311: Standard pseudo-random generators

**Issue**: Using `random` module for security-sensitive operations.

**Fix**:
```python
# Before
import random
token = random.randint(1000, 9999)

# After
import secrets
token = secrets.randbelow(9000) + 1000
```

### E302: Expected 2 blank lines

**Issue**: Missing blank lines between top-level function/class definitions.

**Fix**:
```python
# Before
def function1():
    pass
def function2():
    pass

# After
def function1():
    pass


def function2():
    pass
```

## Continuous Integration

The repository uses GitHub Actions for automated code scanning:

### Codacy Workflow

Location: `.github/workflows/codacy.yml`

This workflow:
- Runs on manual trigger (workflow_dispatch)
- Executes Codacy Analysis CLI
- Uploads results to GitHub Code Scanning
- Can be triggered manually from the Actions tab

### Running Codacy Workflow

```bash
# Via GitHub UI:
# 1. Go to Actions tab
# 2. Select "Codacy Security Scan"
# 3. Click "Run workflow"

# Via gh CLI:
gh workflow run "Codacy Security Scan"
```

## Best Practices

1. **Run scans before committing**: Use pre-commit hooks to catch issues early
2. **Fix issues incrementally**: Don't let code quality debt accumulate
3. **Prioritize security issues**: Address high and medium severity security issues first
4. **Document exceptions**: If you need to ignore a warning, document why
5. **Update scanning tools**: Keep Bandit, Flake8, and other tools up to date

## References

- [Flake8 Documentation](https://flake8.pycqa.org/)
- [Bandit Documentation](https://bandit.readthedocs.io/)
- [Codacy Documentation](https://docs.codacy.com/)
- [Pre-commit Documentation](https://pre-commit.com/)
