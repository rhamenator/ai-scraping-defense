# DevSecOps Integration Guide

This document describes the comprehensive DevSecOps integration implemented in the AI Scraping Defense project. The integration follows shift-left security principles and implements security gates throughout the development lifecycle.

## Overview

Our DevSecOps implementation includes:

1. **Security Gates** - Automated security checks that block builds on critical issues
2. **Shift-Left Security** - Security checks integrated early in development
3. **Security Automation** - Automated security scanning and remediation
4. **Continuous Security Monitoring** - Ongoing security posture tracking
5. **Security Metrics** - Quantifiable security measurements

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Developer Workstation                     │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐ │
│  │  Pre-commit    │  │   IDE Plugins  │  │  Local Scans │ │
│  │    Hooks       │  │   (Snyk, etc)  │  │              │ │
│  └────────────────┘  └────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Version Control (Git)                    │
└─────────────────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Pull Request Created                      │
└─────────────────────────────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Security Gate (Automated Checks)               │
│  ┌───────────┐ ┌───────────┐ ┌──────────┐ ┌─────────────┐ │
│  │  Secret   │ │   SAST    │ │Dependency│ │ Container   │ │
│  │ Scanning  │ │ (Semgrep) │ │Scanning  │ │  Scanning   │ │
│  │(Gitleaks) │ │ (Bandit)  │ │(pip-audit│ │  (Trivy)    │ │
│  └───────────┘ └───────────┘ └──────────┘ └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            ▼
                    ┌──────────────┐
                    │ Gate Passed? │
                    └──────────────┘
                      │          │
                   YES│          │NO
                      ▼          ▼
            ┌──────────────┐  ┌──────────────┐
            │   Run CI/CD  │  │ Block & Alert│
            │    Tests     │  │   Developer  │
            └──────────────┘  └──────────────┘
                      ▼
            ┌──────────────┐
            │    Deploy    │
            └──────────────┘
```

## Components

### 1. Security Gate Workflow

**Location**: `.github/workflows/security-gate.yml`

The security gate is the primary enforcement mechanism that runs on every pull request and push to main branches. It performs comprehensive security scanning and enforces quality thresholds.

**Features**:
- Secret detection with Gitleaks
- SAST with Semgrep and Bandit
- Dependency vulnerability scanning
- Container security scanning
- Configurable severity thresholds
- Automated PR comments with findings
- GitHub Security tab integration

**Thresholds** (configurable in `.github/security-policy.yml`):
- Critical: 0 issues allowed (always blocks)
- High: 0 issues allowed (blocks by default)
- Medium: 10 issues allowed
- Low: 50 issues allowed
- Secrets: 0 allowed (always blocks)

### 2. Pre-commit Hooks (Shift-Left)

**Location**: `.pre-commit-config.yaml`

Security checks run locally before code is committed, catching issues early.

**Hooks**:
- **Gitleaks**: Detects secrets in code changes
- **Bandit**: Python security vulnerability scanner
- **Safety**: Python dependency vulnerability checker
- **detect-private-key**: Detects private keys in commits

**Setup**:
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

### 3. Security Policy Configuration

**Location**: `.github/security-policy.yml`

Central configuration file for all security settings, thresholds, and tool configurations.

**Sections**:
- `security_gate`: Gate thresholds and blocking rules
- `tools`: Tool-specific configurations
- `shift_left`: Shift-left practices and IDE integration
- `automation`: Auto-fix and auto-triage settings
- `compliance`: Compliance standards and requirements
- `reporting`: Report generation and retention

### 4. Security Metrics Collection

**Location**: `scripts/security/security_metrics.py`

Automated security metrics collection and reporting system.

**Usage**:
```bash
# Generate metrics from security scan reports
python scripts/security/security_metrics.py \
    --reports-dir reports/security-gate \
    --output security-metrics.json \
    --summary

# View security score
python scripts/security/security_metrics.py --summary
```

**Metrics Tracked**:
- Total security issues by severity
- Security score (0-100)
- Tool-specific findings
- Trend analysis over time
- Secret exposure incidents

### 5. CI/CD Integration

**Enhanced Workflows**:
- `ci-tests.yml`: Integrated with security gate
- `security-controls.yml`: Scheduled security scans
- `comprehensive-security-audit.yml`: Deep security analysis
- `security-autofix.yml`: Automated security fixes

## Security Scanning Tools

### Secret Scanning
- **Gitleaks**: Detects hardcoded secrets, API keys, passwords
- **Runs**: Pre-commit, CI/CD, scheduled
- **Action**: Blocks on any detection

### SAST (Static Application Security Testing)
- **Semgrep**: Pattern-based security analysis
- **Bandit**: Python-specific security scanner
- **Runs**: Pre-commit, CI/CD
- **Action**: Blocks on critical/high severity

### Dependency Scanning
- **pip-audit**: Python dependency vulnerabilities
- **Safety**: Additional Python dependency checking
- **npm audit**: Node.js dependencies
- **Runs**: CI/CD, scheduled
- **Action**: Blocks on critical/high severity

### Container Scanning
- **Trivy**: Container image and filesystem vulnerabilities
- **Runs**: CI/CD, deployment
- **Action**: Blocks on critical/high severity

## Security Score

The security score is calculated as:

```
Score = 100 - (Critical × 10 + High × 5 + Medium × 2 + Low × 0.5 + Secrets × 20)
Score = max(0, Score)
```

**Interpretation**:
- **90-100**: Excellent security posture
- **75-89**: Good security posture
- **60-74**: Acceptable, needs improvement
- **Below 60**: Poor, requires immediate attention

## Workflow Triggers

### Automatic Triggers
- **Pull Requests**: Security gate runs on all PRs to main/develop
- **Push to main/develop**: Full security audit
- **Scheduled**: Daily security scans at 06:00 UTC
- **Dependency updates**: Security scan on dependency changes

### Manual Triggers
- **workflow_dispatch**: Manual trigger via GitHub UI
- **Custom severity**: Override default thresholds

## Configuration

### Adjusting Security Thresholds

Edit `.github/security-policy.yml`:

```yaml
security_gate:
  severity_threshold: high  # critical, high, medium, low
  thresholds:
    critical: 0
    high: 0
    medium: 10
    low: 50
```

### Disabling Specific Checks

For Bandit (Python security):

Edit `pyproject.toml`:

```toml
[tool.bandit]
skips = ["B404"]  # Skip specific Bandit check
```

For pre-commit hooks:

Comment out or remove the hook in `.pre-commit-config.yaml`

### Allowlisting False Positives

Create `.github/triage/allowlist.yml`:

```yaml
false_positives:
  - "rule-id-1"
  - "rule-id-2"

won_t_fix:
  - path: "test/"
    rules:
      - "test-specific-issue"

used_in_tests:
  - path: "test/fixtures/"
    rules:
      - "insecure-pattern"
```

## Best Practices

### 1. Run Security Checks Locally

Always run security checks before pushing:

```bash
# Run pre-commit hooks
pre-commit run --all-files

# Run Bandit locally
bandit -r src/ -ll

# Run Gitleaks
gitleaks detect -v
```

### 2. Fix Security Issues Immediately

- Critical and High severity issues should be fixed immediately
- Medium severity issues should be tracked and fixed in next sprint
- Low severity issues should be addressed in regular maintenance

### 3. Keep Dependencies Updated

```bash
# Check for outdated dependencies
pip list --outdated

# Audit dependencies
pip-audit

# Update safely
pip install --upgrade package-name
```

### 4. Regular Security Reviews

- Review security metrics weekly
- Conduct security audits monthly
- Update security policies quarterly

### 5. Security Training

- Ensure team is familiar with OWASP Top 10
- Conduct secure coding training
- Review security findings in retrospectives

## Troubleshooting

### Security Gate Failing

1. **Check the workflow run logs**:
   - Go to Actions tab → Security Gate workflow
   - Review detailed findings

2. **Review security reports**:
   - Download artifacts from workflow run
   - Examine JSON reports for details

3. **Common issues**:
   - Hardcoded secrets: Remove and use environment variables
   - High severity findings: Fix code vulnerabilities
   - Dependency vulnerabilities: Update dependencies

### Pre-commit Hook Issues

```bash
# Update hooks
pre-commit autoupdate

# Clear cache
pre-commit clean

# Reinstall
pre-commit uninstall
pre-commit install
```

### False Positives

1. Add to allowlist in `.github/triage/allowlist.yml`
2. Document why it's a false positive
3. Run security-triage workflow to dismiss alerts

## Integration with Other Systems

### Slack Notifications

Configure in `.github/security-policy.yml`:

```yaml
automation:
  notifications:
    slack_webhook: ${{ secrets.SLACK_WEBHOOK }}
```

### Security Dashboard

Metrics are automatically uploaded to:
- GitHub Security tab (SARIF format)
- Artifact storage (JSON reports)
- Optional: External dashboards (Grafana, etc.)

### Issue Tracking

Security issues can auto-create GitHub issues:

```yaml
automation:
  notifications:
    create_issues: true
```

## Compliance

The DevSecOps implementation helps meet requirements for:

- **OWASP Top 10**: Continuous scanning for web vulnerabilities
- **CWE Top 25**: Detection of common weakness enumeration
- **PCI-DSS**: Security controls for payment processing
- **SOC 2**: Security monitoring and incident response

## Metrics and Reporting

### Available Reports

1. **Security Gate Report**: Per-PR security status
2. **Security Metrics**: Aggregated security posture
3. **Trend Analysis**: Security improvements over time
4. **Tool-specific Reports**: Detailed findings per scanner

### Accessing Reports

```bash
# Download from workflow artifacts
gh run download <run-id> -n security-gate-reports

# View in GitHub UI
# Navigate to: Actions → Workflow Run → Artifacts
```

## Further Reading

- [OWASP DevSecOps Guidelines](https://owasp.org/www-project-devsecops-guideline/)
- [Shift Left Security](https://www.microsoft.com/en-us/securityengineering/sdl/)
- [GitHub Security Features](https://docs.github.com/en/code-security)

## Support

For questions or issues with the DevSecOps integration:

1. Check this documentation
2. Review security-related issues in the repository
3. Contact the security team
4. Create a new issue with the `security` label
