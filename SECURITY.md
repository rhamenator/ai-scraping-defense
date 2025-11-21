# Security Policy

## Supported Versions

We are committed to maintaining the security of the AI Scraping Defense Stack. Security updates will be applied to the following versions:

| Version | Supported          |
| :------ | :----------------- |
| Latest  | :white_check_mark: |
| < 1.0   | :warning: Best Effort |

We encourage users to stay on the latest stable release for the most up-to-date security patches.

## Reporting a Vulnerability

We appreciate responsible disclosure of security vulnerabilities. If you discover a potential security issue in this project:

1. **Do NOT open a public GitHub issue.** Public disclosure could put users at risk before a fix is available.
2. **Email us directly** at **[rhamenator@gmail.com]**.
3. **Provide detailed information** in your report, including:
    * A clear description of the vulnerability.
    * Steps to reproduce the issue (code snippets, configurations, or sequences of requests are helpful).
    * The potential impact if the vulnerability is exploited.
    * Any suggested mitigation or fix, if you have one.

We aim to acknowledge receipt of your report within **72 hours**. We will investigate the issue and communicate with you regarding the triage status, potential timelines for a fix, and coordinate disclosure if necessary.

We may recognize your contribution publicly once the vulnerability is addressed, unless you prefer to remain anonymous.

## Security Practices

* We strive to follow secure coding practices.
* Dependencies are periodically reviewed (consider adding automated checks like Dependabot).
* Container images are built from trusted base images.
* The Admin UI requires explicit CORS origins. Set `ADMIN_UI_CORS_ORIGINS` to allowed hosts (default `http://localhost`) and avoid using `*` when credentials are allowed.

## Vulnerability Management

### Automated Vulnerability Scanning

We employ comprehensive automated vulnerability scanning across multiple layers:

* **Python Dependencies**: Weekly automated scans using `pip-audit` and `safety` check
* **Container Images**: Continuous scanning with Trivy for container vulnerabilities
* **Code Analysis**: Static analysis with Bandit, Semgrep, and CodeQL
* **Infrastructure**: Terraform and Kubernetes configuration scanning
* **Secrets Detection**: Gitleaks and TruffleHog for credential exposure

### Vulnerability Prioritization

Vulnerabilities are prioritized based on:

1. **CVSS Score**: Critical (9.0-10.0), High (7.0-8.9), Medium (4.0-6.9), Low (0.1-3.9)
2. **Exploitability**: Active exploits in the wild receive highest priority
3. **Exposure**: Public-facing components are prioritized over internal services
4. **Data Sensitivity**: Issues affecting authentication, authorization, or data protection
5. **Patch Availability**: Whether fixes are available and tested

### Patch Management

Our patch management process:

* **Critical Vulnerabilities**: Addressed within 24-48 hours
* **High Vulnerabilities**: Patched within 7 days
* **Medium Vulnerabilities**: Addressed within 30 days
* **Low Vulnerabilities**: Evaluated and patched in regular maintenance cycles

Patches are:
1. Tested in staging environments first
2. Deployed using blue-green or canary deployment strategies
3. Monitored for regressions post-deployment
4. Documented in CHANGELOG.md and release notes

### Vulnerability Reporting

#### For Users
Check vulnerability status:
* Review GitHub Security Advisories on our repository
* Check the `reports/` directory from CI/CD runs for detailed scan results
* Monitor our CHANGELOG.md for security-related updates

#### Automated Reporting
Our CI/CD pipeline automatically:
* Generates SARIF reports uploaded to GitHub Security tab
* Creates detailed vulnerability reports as workflow artifacts
* Updates GitHub Step Summaries with vulnerability counts by severity
* Maintains a 90-day retention of detailed vulnerability reports

### Dependency Management

We maintain secure dependencies through:

* **requirements.txt**: Primary dependency specifications with version constraints
* **requirements.lock**: Pinned versions for reproducible builds (generated via pip-compile)
* **constraints.txt**: Additional version constraints for transitive dependencies
* **Automated Updates**: Dependabot and scheduled workflows check for updates
* **Security Review**: All dependency updates undergo security review before merging

### Running Security Scans Locally

To run vulnerability scans locally:

```bash
# Python dependency scan
pip install pip-audit safety
pip-audit -r requirements.txt --desc on
safety check -r requirements.txt --full-report

# Container scan
trivy image your-image-name

# Code security scan
bandit -r src/ -f json -o security-report.json
semgrep --config=p/security-audit src/

# Comprehensive scan (Linux)
sudo ./scripts/linux/security_scan.sh localhost
```

See `docs/security_scan.md` for detailed documentation on security scanning tools and procedures.

Thank you for helping keep the AI Scraping Defense Stack secure!
