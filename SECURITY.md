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
2. **Email us directly** at **[rhamenator@gmail.com]**. Make sure to encrypt your finding, if possible. Use our PGP key: `TODO: insert PGP key here`
3. **Provide detailed information** in your report, including:
    * A clear description of the vulnerability.
    * Steps to reproduce the issue (code snippets, configurations, or sequences of requests are helpful).
    * The potential impact if the vulnerability is exploited.
    * Any suggested mitigation or fix, if you have one.

We aim to acknowledge receipt of your report within **72 hours**. We will investigate the issue and communicate with you regarding the triage status, potential timelines for a fix, and coordinate disclosure if necessary.

We may recognize your contribution publicly once the vulnerability is addressed, unless you prefer to remain anonymous.

## Security Practices

*   We strive to follow secure coding practices.
*   Dependencies are periodically reviewed (consider adding automated checks like Dependabot).
*   Container images are built from trusted base images.
*   The Admin UI requires explicit CORS origins. Set `ADMIN_UI_CORS_ORIGINS` to allowed hosts (default `http://localhost`) and avoid using `*` when credentials are allowed.
*   We use a configuration file (`config/security_hardening.yaml`) to manage security settings.
*   Security compliance is regularly monitored using automated workflows.

## Secret Management

### Best Practices

**DO:**
* Use dedicated secret management tools (HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, Google Secret Manager, Kubernetes Secrets)
* Encrypt secrets at rest using industry-standard encryption (AES-256)
* Implement proper access controls and audit logging for secret access
* Use environment-specific secrets (development, staging, production)
* Rotate secrets regularly according to your security policy
* Use secret files mounted as volumes rather than environment variables when possible
* Store secrets in encrypted backends with restricted permissions (file mode 600 or stricter)

**DO NOT:**
* Commit secrets to version control (use `.gitignore` for secret files)
* Log secrets to stdout, stderr, or log files
* Store secrets in plaintext configuration files
* Share secrets via insecure channels (email, chat, unencrypted files)
* Use the same secrets across multiple environments
* Store secrets in container images

### Secret Generation

When using the provided secret generation scripts (`scripts/linux/generate_secrets.sh` or `scripts/windows/Generate-Secrets.ps1`):

1. **Generated secrets are for development/testing only.** For production deployments, integrate with a proper secret management solution.

2. **Protect exported secret files:**
   - The `--export-path` option creates a JSON file with generated credentials
   - This file is automatically set to mode 600 (owner read/write only)
   - Store this file in a secure location and delete after importing to your secret manager
   - Never commit this file to version control

3. **Key rotation:** Implement regular secret rotation schedules:
   - Database passwords: Every 90 days minimum
   - API keys: Every 90 days or per provider recommendations
   - Admin credentials: Every 60 days
   - System seeds: Every 180 days (requires service restart)

4. **Encryption at rest:**
   - Use encrypted filesystems for secret storage
   - Enable encryption for Kubernetes Secrets (encryption at rest)
   - Use sealed secrets or external secret operators in Kubernetes
   - Consider using tools like `sops` (Secrets OPerationS) or `git-crypt` for encrypted repository secrets

### Production Secret Management

For production environments, we recommend:

1. **Kubernetes Deployments:**
   - Use External Secrets Operator with your cloud provider's secret manager
   - Enable encryption at rest for etcd
   - Use Sealed Secrets or SOPS for GitOps workflows
   - Implement RBAC policies restricting secret access

2. **Docker Compose/VM Deployments:**
   - Use HashiCorp Vault or similar solution
   - Mount secrets as read-only files from encrypted storage
   - Use Docker secrets feature for swarm mode
   - Implement secret rotation automation

3. **Cloud Platforms:**
   - AWS: Use AWS Secrets Manager or Systems Manager Parameter Store
   - Azure: Use Azure Key Vault
   - GCP: Use Google Secret Manager
   - Integrate with IAM roles and service accounts for access control

### Audit and Compliance

* All secret access should be logged to audit trails
* Regularly review secret usage and access patterns
* Implement alerting for unusual secret access
* Document your secret rotation procedures
* Maintain an inventory of all secrets and their rotation schedules

Thank you for helping keep the AI Scraping Defense Stack secure!
