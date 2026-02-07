# Secret Management with HashiCorp Vault

This document describes the comprehensive secret management system with HashiCorp Vault integration.

## Overview

The AI Scraping Defense system includes a multi-layered secret management approach:

1. **HashiCorp Vault Integration** - Central secret storage with encryption at rest
2. **Automated Secret Rotation** - Policy-based rotation with configurable schedules
3. **Lifecycle Management** - Version tracking, expiration monitoring, and cleanup
4. **Compliance Monitoring** - Real-time compliance checks with Prometheus metrics
5. **Audit Logging** - Complete audit trail for all secret operations

## Quick Start

### 1. Generate Secrets Locally

```bash
# Generate secrets and update .env file
./scripts/generate_secrets.sh --update-env

# Generate and export to JSON
./scripts/generate_secrets.sh --export-path /secure/location/secrets.json
```

### 2. Using Vault

```bash
# Store secrets in Vault
./scripts/generate_secrets.sh --vault \
  --vault-addr https://vault.example.com:8200 \
  --vault-token $VAULT_TOKEN \
  --vault-path ai-defense/production

# Configure application to use Vault
export VAULT_ADDR=https://vault.example.com:8200
export VAULT_TOKEN=your-token
# or use AppRole/Kubernetes auth (see Configuration section)
```

## Architecture

### Vault Client (`src/shared/vault_client.py`)

The `VaultClient` class provides:

- **Multiple Authentication Methods**:
  - Token authentication (development/testing)
  - AppRole authentication (applications)
  - Kubernetes authentication (K8s deployments)

- **KV v2 Operations**:
  - Read/Write secrets with versioning
  - List secrets at a path
  - Delete/Destroy versions
  - Read metadata (creation time, versions)

- **Error Handling**:
  - Automatic retry with exponential backoff
  - Graceful fallback to file-based secrets
  - Comprehensive error logging

### Secret Rotation Service (`src/security/secret_rotation.py`)

Automated rotation with:

- **Rotation Policies**: Per-secret configuration
  - Rotation period (days)
  - Password complexity requirements
  - Custom generators for special formats

- **Hooks**: Pre/post rotation callbacks
  - Update dependent services
  - Invalidate caches
  - Send notifications

- **Default Policies**:
  - Database passwords: 90 days
  - Admin credentials: 90 days
  - JWT secrets: 90 days
  - System seed: 180 days

### Lifecycle Management (`src/security/secret_lifecycle.py`)

Manages the full secret lifecycle:

- **Age Tracking**: Monitor secret age in days
- **Expiration Warnings**: Configurable warning periods
- **Version Cleanup**: Automatic pruning of old versions
- **Status Reports**: Comprehensive lifecycle status

### Compliance Monitoring (`src/security/secret_compliance.py`)

Ensures secrets meet security policies:

- **Compliance Checks**:
  - Age compliance (max age limits)
  - Version compliance (max version count)
  - Rotation tracking (metadata presence)

- **Prometheus Metrics**:
  - `vault_secret_age_days`
  - `vault_secret_compliance_score`
  - `vault_secret_rotation_total`
  - `vault_secret_version_count`
  - `vault_secret_access_total`
  - `vault_secret_operation_duration_seconds`

- **Compliance Scoring**: 0-100 scale
  - 100: Fully compliant
  - 70-99: Minor warnings
  - 0-69: Critical issues

## Configuration

### Environment Variables

```bash
# Vault Server
VAULT_ADDR=https://vault.example.com:8200
VAULT_NAMESPACE=your-namespace  # Enterprise only

# Authentication (choose one method)
VAULT_TOKEN=s.xxxxxxxxxxxxx                    # Token auth
VAULT_ROLE_ID=xxx VAULT_SECRET_ID=yyy          # AppRole auth
VAULT_KUBERNETES_ROLE=ai-defense               # K8s auth

# Configuration
VAULT_MOUNT_POINT=secret                       # KV mount point
VAULT_VERIFY_TLS=true                          # TLS verification
VAULT_TIMEOUT=30                               # Operation timeout
```

### Secret Path References

Use `_VAULT_PATH` suffix for Vault-backed secrets:

```bash
# Instead of file paths:
REDIS_PASSWORD_FILE=/run/secrets/redis_password.txt

# Use Vault paths:
REDIS_PASSWORD_FILE_VAULT_PATH=secret/data/ai-defense/database/redis
```

The system automatically:
1. Tries to read from Vault
2. Falls back to file-based secrets
3. Extracts the configured key (default: "value")

### Helm Configuration

**Staging** (`helm/values-staging.yaml`):
```yaml
vault:
  enabled: false
  address: http://vault:8200
  authMethod: kubernetes
  role: ai-defense-staging
  secretPath: secret/data/ai-defense/staging
```

**Production** (`helm/values-production.yaml`):
```yaml
vault:
  enabled: true
  address: https://vault.production.internal:8200
  authMethod: kubernetes
  role: ai-defense-production
  secretPath: secret/data/ai-defense/production
  verifyTLS: true
```

## Usage Examples

### Reading Secrets

```python
from src.shared.vault_client import get_vault_client

# Get client (singleton)
vault = get_vault_client()

# Read entire secret
secret = vault.read_secret("database/postgres")
print(secret["password"])

# Get single value
password = vault.get_secret_value("database/postgres", "password")

# Read specific version
old_secret = vault.read_secret("database/postgres", version=5)
```

### Writing Secrets

```python
# Write new secret
vault.write_secret("myapp/api", {
    "key": "api_key_value",
    "endpoint": "https://api.example.com"
})

# Update with check-and-set (optimistic locking)
vault.write_secret("myapp/api", {"key": "new_value"}, cas=3)
```

### Secret Rotation

```python
from src.security.secret_rotation import (
    SecretRotationService,
    SecretRotationPolicy
)

# Create rotation service
service = SecretRotationService()

# Define policy
policy = SecretRotationPolicy(
    name="database_password",
    path="database/postgres",
    key_name="password",
    rotation_period_days=90,
    min_length=32,
    include_special=True
)

# Rotate secret
result = service.rotate_secret(policy, force=False)
if result["success"]:
    print(f"Secret rotated: {result['message']}")
```

### Lifecycle Management

```python
from src.security.secret_lifecycle import (
    SecretLifecycleManager,
    SecretLifecycleConfig
)

# Create manager
manager = SecretLifecycleManager()

# Check secret age
age = manager.get_secret_age("database/postgres")
print(f"Secret age: {age.days} days")

# Cleanup old versions
config = SecretLifecycleConfig(
    path="database/postgres",
    max_versions=10,
    auto_cleanup=True
)
result = manager.cleanup_old_versions(config.path, config.max_versions)
print(f"Deleted {len(result['versions_deleted'])} old versions")
```

### Compliance Monitoring

```python
from src.security.secret_compliance import (
    SecretComplianceMonitor,
    SecretCompliancePolicy
)

# Create monitor
monitor = SecretComplianceMonitor()

# Check compliance
policy = SecretCompliancePolicy(
    path="database/postgres",
    max_age_days=90,
    max_versions_to_keep=10,
    require_rotation_tracking=True
)

result = monitor.check_compliance(policy)
print(f"Compliance Status: {result['status']}")
print(f"Compliance Score: {result['score']}/100")

# Generate report for all secrets
from src.security.secret_compliance import create_default_compliance_policies
report = monitor.generate_compliance_report(create_default_compliance_policies())
print(f"Compliant: {report['compliant']}/{report['total_secrets']}")
```

## Operational Procedures

### Initial Setup

1. **Deploy Vault** (or use existing instance)
2. **Enable KV v2 secrets engine**:
   ```bash
   vault secrets enable -path=secret kv-v2
   ```

3. **Create policies**:
   ```hcl
   # ai-defense-policy.hcl
   path "secret/data/ai-defense/*" {
     capabilities = ["create", "read", "update", "delete", "list"]
   }
   path "secret/metadata/ai-defense/*" {
     capabilities = ["list", "read"]
   }
   ```

4. **Configure authentication**:
   ```bash
   # For Kubernetes
   vault auth enable kubernetes
   vault write auth/kubernetes/role/ai-defense \
     bound_service_account_names=ai-defense \
     bound_service_account_namespaces=ai-defense \
     policies=ai-defense-policy \
     ttl=24h
   ```

5. **Generate and store secrets**:
   ```bash
   ./scripts/generate_secrets.sh --vault
   ```

### Regular Maintenance

**Daily**:
- Monitor Prometheus metrics for secret age and compliance
- Review audit logs for unusual access patterns

**Weekly**:
- Generate compliance reports
- Review secrets approaching expiration

**Monthly**:
- Rotate secrets based on policies
- Clean up old secret versions
- Review and update rotation policies

### Incident Response

**Secret Compromise**:
1. Immediately rotate affected secret: `./scripts/generate_secrets.sh --vault`
2. Review audit logs: `grep secret_access /app/logs/audit.log`
3. Update dependent services with new credentials
4. Investigate access patterns and entry point

**Vault Unavailable**:
1. System falls back to file-based secrets automatically
2. Monitor logs for Vault connection errors
3. Restore Vault connectivity
4. Verify secret synchronization

## Security Best Practices

1. **Never commit secrets** to version control
2. **Use AppRole or Kubernetes auth** in production (not tokens)
3. **Enable TLS** for all Vault connections
4. **Rotate secrets regularly** (90 days for most, 30 days for high-risk)
5. **Monitor compliance metrics** via Prometheus/Grafana
6. **Audit logs regularly** for unauthorized access
7. **Use namespaces** in Vault Enterprise for tenant isolation
8. **Implement least privilege** access policies
9. **Enable secret versioning** for rollback capability
10. **Test disaster recovery** procedures regularly

## Monitoring and Alerts

### Prometheus Queries

```promql
# Secrets older than 80 days
vault_secret_age_days > 80

# Low compliance scores
vault_secret_compliance_score < 70

# Recent rotation failures
increase(vault_secret_rotation_total{status="failure"}[1h]) > 0

# High access rate
rate(vault_secret_access_total[5m]) > 10
```

### Grafana Dashboard

Create dashboards with:
- Secret age gauges
- Compliance score trends
- Rotation success rates
- Access patterns by path
- Version count distributions

## Troubleshooting

### Vault Connection Issues

```bash
# Check connectivity
curl -s $VAULT_ADDR/v1/sys/health | jq

# Verify authentication
vault token lookup

# Test secret read
vault kv get -mount=secret ai-defense/database/postgres
```

### Rotation Failures

```python
# Check rotation status
from src.security.secret_rotation import SecretRotationService, create_default_policies
service = SecretRotationService()
statuses = service.get_rotation_status(create_default_policies())
for status in statuses:
    print(f"{status['policy_name']}: rotation_due={status['rotation_due']}")
```

### Compliance Issues

```bash
# Generate detailed compliance report
python -c "
from src.security.secret_compliance import SecretComplianceMonitor, create_default_compliance_policies
monitor = SecretComplianceMonitor()
report = monitor.generate_compliance_report(create_default_compliance_policies())
import json
print(json.dumps(report, indent=2))
"
```

## Migration Guide

### From File-Based to Vault

1. **Install and configure Vault** (see Initial Setup)
2. **Migrate existing secrets**:
   ```bash
   # Read from .env and store in Vault
   ./scripts/generate_secrets.sh --vault --update-env
   ```

3. **Update configuration** to use Vault paths:
   ```bash
   # In .env or environment
   VAULT_ADDR=https://vault.example.com:8200
   VAULT_TOKEN=your-token
   REDIS_PASSWORD_FILE_VAULT_PATH=secret/data/ai-defense/database/redis
   ```

4. **Test fallback** by temporarily disabling Vault
5. **Remove file-based secrets** once validated
6. **Enable monitoring** and rotation policies

### Rollback Procedure

If needed, revert to file-based secrets:

1. Export secrets from Vault: `./scripts/generate_secrets.sh --export-path /tmp/secrets.json`
2. Remove Vault environment variables
3. Restore file-based secret paths
4. Restart services

## API Reference

See module docstrings for complete API:
- `src/shared/vault_client.py` - Vault client operations
- `src/security/secret_rotation.py` - Rotation service
- `src/security/secret_lifecycle.py` - Lifecycle management
- `src/security/secret_compliance.py` - Compliance monitoring

## Support

For issues or questions:
1. Check logs: `/app/logs/audit.log` and service logs
2. Review Prometheus metrics
3. Consult this documentation
4. Open an issue on GitHub
