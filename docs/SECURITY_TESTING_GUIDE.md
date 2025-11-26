# Security Testing Quick Start Guide

## Overview

This guide provides quick instructions for running security tests on the AI Scraping Defense stack.

## Prerequisites

### Install Security Tools

Run the setup script to install all required security testing tools:

```bash
sudo ./scripts/linux/security_setup.sh
```

This installs 25+ security tools including:
- Network scanners (nmap, masscan)
- Web scanners (nikto, ZAP, gobuster, ffuf)
- Container scanners (Trivy, Grype)
- Code analyzers (Bandit, Gitleaks)
- And many more...

## Quick Start

### 1. Start the Stack

```bash
docker-compose up -d
```

Wait for all services to be healthy (~30 seconds).

### 2. Run Static Security Checks

Validate configuration security without starting services:

```bash
python scripts/security/run_static_security_checks.py
```

This checks:
- Docker compose security settings
- Nginx configuration
- Secret management
- Service hardening

**Expected Output:**
```
All static security checks passed.
```

### 3. Run Dynamic Security Scan

Scan running services for vulnerabilities:

```bash
# Basic scan (network and web)
sudo ./scripts/linux/security_scan.sh localhost http://localhost

# Comprehensive scan with all parameters
sudo ./scripts/linux/security_scan.sh \
  localhost \
  http://localhost:80 \
  ai-scraping-defense:latest \
  . \
  "http://localhost/api/test?id=1"
```

**Parameters:**
1. `localhost` - Target host/IP for network scans
2. `http://localhost:80` - Web URL for web application scans
3. `ai-scraping-defense:latest` - Docker image to scan (optional)
4. `.` - Source code directory for static analysis (optional)
5. `"http://localhost/api/test?id=1"` - URL for SQLMap testing (optional)

### 4. Review Results

All scan results are saved in the `reports/` directory:

```bash
ls -lh reports/
```

Common report files:
- `nmap_localhost.txt` - Network scan results
- `nikto_*.txt` - Web server vulnerabilities
- `zap_*.html` - OWASP ZAP scan results
- `bandit_*.txt` - Python code security issues
- `trivy_*.txt` - Container vulnerabilities
- `gitleaks_*.txt` - Secret scanning results
- `pip_audit.txt` - Python dependency vulnerabilities

## Test Scenarios

### Scenario 1: Pre-Deployment Security Check

Before deploying to production:

```bash
# 1. Static checks
python scripts/security/run_static_security_checks.py

# 2. Dependency scan
pip-audit -r requirements.txt

# 3. Code analysis
bandit -r src/ -f txt -o reports/bandit_precheck.txt

# 4. Secret scan
gitleaks detect -s . -v --report-path reports/gitleaks_precheck.txt

# 5. Container scan
trivy image ai-scraping-defense:latest
```

### Scenario 2: Penetration Test Preparation

Full security assessment:

```bash
# Start services
docker-compose up -d

# Run comprehensive scan
sudo ./scripts/linux/security_scan.sh \
  localhost \
  http://localhost:80 \
  ai-scraping-defense:latest \
  . \
  "http://localhost/api/vulnerable?param=test"

# Review all reports
grep -i "critical\|high\|severe" reports/* | less
```

### Scenario 3: Continuous Security Monitoring

Daily/weekly automated checks:

```bash
#!/bin/bash
# Save as scripts/daily_security_check.sh

set -e

echo "Running daily security checks..."

# Static checks
python scripts/security/run_static_security_checks.py

# Dependency updates check
pip-audit -r requirements.txt

# Docker image security
docker images -q | xargs -I {} trivy image {}

# Secret scanning
gitleaks detect -s . -v

echo "Security checks complete. Review reports/ directory."
```

### Scenario 4: API Security Testing

Focus on API endpoints:

```bash
# Start services
docker-compose up -d

# Wait for services to be ready
sleep 10

# Test admin UI API
sudo ./scripts/linux/security_scan.sh \
  localhost \
  http://localhost:5002 \
  "" \
  "" \
  "http://localhost:5002/api/endpoint?test=1"

# Test cloud dashboard API
sudo ./scripts/linux/security_scan.sh \
  localhost \
  http://localhost:5006

# Check for common API vulnerabilities
cd reports/ && grep -i "api\|token\|auth\|injection" * | tee api_issues.txt
```

## Individual Tool Usage

### Network Scanning

```bash
# Quick port scan
nmap -A -p 22,80,443,5432,6379 localhost

# Fast sweep
masscan -p22,80,443,5432,6379 localhost --rate=1000
```

### Web Application Scanning

```bash
# Nikto web scan
nikto -host http://localhost

# OWASP ZAP baseline
zap-baseline.py -t http://localhost

# Directory enumeration
gobuster dir -u http://localhost -w /usr/share/wordlists/dirb/common.txt

# Parameter fuzzing
ffuf -w /usr/share/seclists/Discovery/Web-Content/common.txt \
     -u http://localhost/FUZZ
```

### Container Security

```bash
# Trivy vulnerability scan
trivy image ai-scraping-defense:latest

# Grype vulnerability scan
grype ai-scraping-defense:latest
```

### Code Security

```bash
# Python static analysis
bandit -r src/ -f txt

# Secret scanning
gitleaks detect -s . -v

# Dependency vulnerabilities
pip-audit -r requirements.txt
```

### SSL/TLS Testing

```bash
# SSLyze
sslyze --regular localhost:443

# testssl.sh
testssl.sh https://localhost
```

## Interpreting Results

### Severity Levels

- **Critical/High**: Immediate action required
- **Medium**: Should be addressed before production
- **Low/Info**: Review and consider fixing
- **False Positive**: Document and exclude in future scans

### Common Findings

1. **Missing Security Headers** → Configure in nginx.conf
2. **Outdated Dependencies** → Run `pip install -U` for packages
3. **Container Vulnerabilities** → Update base images
4. **SQL Injection Potential** → Review input validation
5. **Weak TLS Configuration** → Update SSL/TLS settings

## Integration with CI/CD

The security scans are already integrated into GitHub Actions:

- `.github/workflows/security-audit.yml` - Regular security audits
- `.github/workflows/comprehensive-security-audit.yml` - Full assessment
- `.github/workflows/pip-audit.yml` - Dependency scanning

To run manually:

```bash
# Trigger security audit workflow
gh workflow run security-audit.yml

# Trigger comprehensive audit
gh workflow run comprehensive-security-audit.yml
```

## Validation Tests

Run the test suite to verify security scan coverage:

```bash
# Run security scan coverage tests
pytest test/test_security_scan_coverage.py -v

# Run all security tests
pytest test/test_security*.py -v

# Run with coverage report
pytest test/test_security*.py --cov=src --cov-report=html
```

## Troubleshooting

### Tools Not Found

If security tools are not installed:

```bash
sudo ./scripts/linux/security_setup.sh
```

### Permission Denied

Most security scans require root:

```bash
sudo ./scripts/linux/security_scan.sh localhost
```

### No Results Generated

Check the reports directory exists:

```bash
mkdir -p reports
```

### Services Not Responding

Ensure services are running:

```bash
docker-compose ps
docker-compose logs
```

## Best Practices

1. **Run Static Checks First**: Catch configuration issues before deployment
2. **Schedule Regular Scans**: Weekly or after major changes
3. **Review All Critical/High Issues**: Don't ignore severity levels
4. **Document False Positives**: Maintain a list of known false positives
5. **Update Tools Regularly**: Security tools need regular updates
6. **Test in Staging First**: Don't run aggressive scans on production
7. **Archive Reports**: Keep historical scan results for comparison
8. **Automate Where Possible**: Use CI/CD for regular scanning

## Additional Resources

- [Security Scan Evaluation Report](./SECURITY_SCAN_EVALUATION.md)
- [Security Policy](../SECURITY.md)
- [Contributing Security Guidelines](../CONTRIBUTING.md)
- [OWASP Testing Guide](https://owasp.org/www-project-web-security-testing-guide/)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)

## Support

For security concerns or questions:

1. Review the [Security Policy](../SECURITY.md)
2. Check existing [security issues](https://github.com/rhamenator/ai-scraping-defense/labels/security)
3. Open a new issue with the `security` label
4. For vulnerabilities, follow the responsible disclosure process in SECURITY.md

---

*This guide is maintained as part of the security testing infrastructure.*
