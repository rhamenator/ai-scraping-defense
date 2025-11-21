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

## Supply Chain Security

We take supply chain security seriously and implement multiple layers of protection:

### Dependency Management
* **Pinned Dependencies**: All dependencies are pinned to specific versions in `requirements.lock` with cryptographic hashes for verification.
* **Regular Audits**: Automated dependency vulnerability scanning runs weekly via `pip-audit` and security workflows.
* **Hash Verification**: Dependencies are verified against known-good hashes during installation.
* **Constraints**: The `constraints.txt` file enforces consistent dependency versions across environments.

### Software Bill of Materials (SBOM)
* We generate and maintain a complete SBOM in CycloneDX and SPDX formats.
* SBOM files are automatically generated during CI/CD and attached to releases.
* The SBOM includes all direct and transitive dependencies with version information.
* Third-party license information is documented in `docs/third_party_licenses.md`.

### Integrity Verification
* **Checksum Validation**: All dependencies are validated against cryptographic hashes during installation.
* **Source Verification**: Dependencies are sourced only from trusted PyPI repositories.
* **Lock Files**: `requirements.lock` ensures reproducible builds with verified dependency trees.

### Supply Chain Monitoring
* **Automated Scanning**: GitHub Actions workflows scan for known vulnerabilities in dependencies.
* **DevSkim Integration**: Static analysis scans for insecure patterns including compromised dependencies.
* **Continuous Monitoring**: Security workflows run on schedule and can be triggered manually.

### Best Practices for Contributors
* Never modify `requirements.lock` manually - regenerate it using `pip-compile`.
* Run `scripts/security/verify_dependencies.py` before committing dependency changes.
* Review the SBOM after updating dependencies to verify no unexpected changes.
* Report any suspicious dependency behavior through our security disclosure process.

Thank you for helping keep the AI Scraping Defense Stack secure!
