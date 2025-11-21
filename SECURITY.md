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

## Security Culture

Our project is committed to fostering a strong security culture where every contributor understands their role in maintaining the security posture of the AI Scraping Defense Stack.

### Security Awareness Training

All contributors are encouraged to:

1. **Complete Security Onboarding**: Review our security documentation including threat models, secure coding guidelines, and incident response procedures.
2. **Stay Informed**: Keep up-to-date with security advisories, CVE databases, and security best practices relevant to our technology stack.
3. **Practice Secure Development**: Follow our secure coding guidelines documented in `CONTRIBUTING.md` and enforce security checks via pre-commit hooks.
4. **Regular Training**: Participate in security training sessions and workshops (see `docs/security/security_awareness_training.md` for curriculum).

### Security Champions Network

We maintain a Security Champions program to promote security awareness across the project:

* **Role**: Security Champions are contributors with heightened security awareness who serve as security advocates within their areas of contribution.
* **Responsibilities**:
  - Review security-related pull requests
  - Participate in security audits and threat modeling sessions
  - Share security knowledge with other contributors
  - Escalate security concerns to maintainers
  - Contribute to security documentation and training materials
* **Becoming a Champion**: Contributors who demonstrate consistent security awareness and make meaningful security contributions may be invited to join the Security Champions network.

For more details, see `docs/security/security_champions.md`.

### Security Culture Measurement

We track and measure our security culture through:

1. **Metrics**:
   - Security issue resolution time (target: <7 days for high severity)
   - Security test coverage (target: >80% for security-critical components)
   - Security training completion rate for active contributors
   - Pre-commit security check compliance rate
   - Number of security findings in code reviews

2. **Regular Assessments**:
   - Quarterly security culture surveys for contributors
   - Monthly security metrics review in maintainer meetings
   - Annual security posture assessment

3. **Continuous Improvement**:
   - Security retrospectives after major releases
   - Post-incident reviews with action items
   - Regular updates to security documentation based on lessons learned

For comprehensive security culture programs and measurement details, see `docs/security/security_culture.md`.

Thank you for helping keep the AI Scraping Defense Stack secure!
