# Legal Compliance Guide

## Overview

This document provides guidance on legal compliance for AI Scraping Defense deployments, with a focus on GDPR (General Data Protection Regulation) compliance.

## GDPR Compliance Framework

### Implemented Features

The AI Scraping Defense system includes a comprehensive GDPR compliance framework:

1. **Consent Management System**
   - Explicit consent tracking for non-essential data processing
   - Consent types: Essential, Analytics, Security, Marketing, Third-Party
   - Timestamp and IP address logging for consent records
   - Consent expiration and renewal management

2. **Right to be Forgotten**
   - Data deletion request workflow
   - Automated data deletion across system components
   - Deletion request tracking and audit trail
   - Support for selective data category deletion

3. **Data Minimization**
   - Automatic anonymization of IP addresses
   - Truncation of user agent strings
   - Retention of only essential data fields
   - Configurable data retention periods

4. **Privacy Impact Assessments (PIAs)**
   - Regular automated compliance reporting
   - Data processing activity documentation
   - Risk assessment and mitigation tracking

5. **Data Protection Officer (DPO)**
   - Designated DPO contact information
   - DPO notification for data breaches
   - DPO oversight of compliance activities

6. **Automated Compliance Reporting**
   - Real-time compliance metrics
   - Audit log generation
   - Consent and deletion statistics
   - Exportable compliance reports

### Configuration

Enable and configure GDPR compliance in your `.env` file:

```bash
# Enable GDPR compliance framework
GDPR_ENABLED=true

# Data Protection Officer contact information
GDPR_DPO_NAME="Data Protection Officer"
GDPR_DPO_EMAIL=dpo@example.com
GDPR_DPO_PHONE="+1-555-0123"

# Data retention period (days)
GDPR_DATA_RETENTION_DAYS=365

# Require explicit consent for non-essential processing
GDPR_CONSENT_REQUIRED=true

# GDPR audit log location
GDPR_AUDIT_LOG_FILE=/app/logs/gdpr_audit.log
```

### Using the GDPR Module

The GDPR compliance manager is available via `src/shared/gdpr.py`:

```python
from src.shared.gdpr import (
    get_gdpr_manager,
    ConsentType,
    DataCategory
)

gdpr = get_gdpr_manager()

# Record user consent
gdpr.record_consent(
    user_id="user123",
    consent_type=ConsentType.ANALYTICS,
    granted=True,
    ip_address="192.168.1.1"
)

# Check consent
has_consent = gdpr.check_consent("user123", ConsentType.ANALYTICS)

# Request data deletion
deletion_request = gdpr.request_data_deletion(
    user_id="user123",
    email="user@example.com",
    data_categories=[DataCategory.IP_ADDRESS, DataCategory.ACCESS_LOGS]
)

# Apply data minimization
minimized_data = gdpr.minimize_data(request_data)

# Generate compliance report
report = gdpr.generate_compliance_report()
```

### Admin UI Integration

The Admin UI includes GDPR management features:
- View and manage user consents
- Process data deletion requests
- Generate compliance reports
- Monitor GDPR audit logs

Access GDPR settings at `/settings` in the Admin UI.

## Data Categories

The system tracks the following personal data categories:

| Category | Description | Legal Basis |
|----------|-------------|-------------|
| IP Address | Network address of requestor | Legitimate Interest |
| User Agent | Browser/client identification | Legitimate Interest |
| Request Headers | HTTP headers for security analysis | Legitimate Interest |
| Access Logs | Timestamps and URLs accessed | Legitimate Interest |
| Authentication | User credentials and sessions | Consent/Contract |
| Payment Info | Payment gateway transactions | Contract |
| Behavioral Data | Advanced bot detection patterns | Consent |

## Legal Bases for Processing

### Legitimate Interest
Security monitoring and protection against malicious actors is processed under legitimate interest:
- Bot detection and prevention
- DDoS attack mitigation
- Security incident response
- System integrity protection

### Consent
Optional features require explicit consent:
- Advanced behavioral analysis
- Marketing communications
- Third-party data sharing
- Analytics beyond essential monitoring

### Legal Obligation
Compliance with applicable cybersecurity and data breach notification laws.

### Contract
Payment processing for pay-per-crawl services.

## Data Subject Rights

The system supports all GDPR data subject rights:

### 1. Right of Access (Article 15)
Users can request copies of their personal data via the Admin UI or DPO contact.

### 2. Right to Rectification (Article 16)
Users can request correction of inaccurate data.

### 3. Right to Erasure (Article 17)
Automated deletion request workflow processes "right to be forgotten" requests.

### 4. Right to Restriction (Article 18)
Users can request limitation of processing.

### 5. Right to Data Portability (Article 20)
Data export in machine-readable format (JSON).

### 6. Right to Object (Article 21)
Users can object to processing based on legitimate interests.

### 7. Rights Related to Automated Decision-Making (Article 22)
Users can contest automated bot detection decisions and request human review.

## Data Retention and Deletion

### Retention Periods
- **Default**: 365 days (configurable)
- **Security Logs**: As required by law
- **Audit Logs**: 7 years for compliance
- **Consent Records**: Duration of consent + 3 years

### Automated Deletion
The system automatically deletes data after retention periods expire:
```python
# Run periodic cleanup
await gdpr.cleanup_expired_data()
```

## Data Breach Notification

In case of a data breach:
1. Assess scope and impact within 24 hours
2. Notify DPO immediately
3. Document breach in GDPR audit log
4. Notify supervisory authority within 72 hours (if required)
5. Notify affected data subjects (if high risk)

Breach notification is logged via:
```python
gdpr._log_gdpr_event("data_breach", {
    "breach_type": "unauthorized_access",
    "affected_records": 100,
    "notification_sent": True
})
```

## International Data Transfers

For deployments transferring data outside EU/EEA:
1. Implement Standard Contractual Clauses (SCCs)
2. Conduct Transfer Impact Assessment (TIA)
3. Document adequacy decisions
4. Update privacy policy with transfer information

## Privacy by Design

The system implements privacy by design principles:
- Data minimization by default
- Pseudonymization of IP addresses
- Encryption in transit and at rest
- Role-based access control (RBAC)
- Regular security audits
- Privacy impact assessments

## Compliance Checklist

Before deployment, ensure:

- [ ] GDPR_ENABLED is set to `true`
- [ ] DPO contact information is configured
- [ ] Data retention period is appropriate for your jurisdiction
- [ ] Privacy policy is published and accessible
- [ ] Consent management is implemented for optional features
- [ ] Data deletion workflow is tested
- [ ] Audit logging is enabled
- [ ] Security measures are documented
- [ ] Staff training on GDPR compliance is completed
- [ ] Incident response plan is in place
- [ ] Regular compliance audits are scheduled

## Additional Regulations

### ePrivacy Directive
For cookie consent and electronic communications:
- Obtain consent before setting non-essential cookies
- Provide clear cookie information
- Allow users to withdraw consent

### CCPA (California)
For California residents:
- Disclose data collection and sharing practices
- Provide opt-out mechanism for data sales
- Respond to deletion requests within 45 days

### Other Jurisdictions
Consult local data protection laws:
- UK GDPR (UK)
- LGPD (Brazil)
- PIPEDA (Canada)
- Privacy Act (Australia)
- APPI (Japan)

## Resources

- [GDPR Official Text](https://gdpr-info.eu/)
- [ICO GDPR Guidance](https://ico.org.uk/for-organisations/guide-to-data-protection/guide-to-the-general-data-protection-regulation-gdpr/)
- [EDPB Guidelines](https://edpb.europa.eu/guidelines/guidelines_en)

## Disclaimer

This guide provides general information only and does not constitute legal advice. Consult with qualified legal counsel to ensure compliance with applicable laws and regulations in your jurisdiction.

## Responsible Use

Use this project responsibly and ensure that all deployments comply with the laws and regulations of your jurisdiction. Review licensing requirements for dependencies and obtain any necessary permissions before monitoring or collecting data.
