# Privacy Policy

**Last Updated:** November 21, 2025

## Overview

This project respects your privacy and complies with the General Data Protection Regulation (GDPR) and other applicable data protection laws. We collect only the minimum information necessary to operate the AI Scraping Defense system effectively.

## Data Controller

The data controller for this system is the organization operating the AI Scraping Defense deployment. For GDPR-related inquiries, please contact:

**Data Protection Officer (DPO)**
- Email: See `GDPR_DPO_EMAIL` configuration
- Phone: See `GDPR_DPO_PHONE` configuration

## Data We Collect

### Essential Data (Legal Basis: Legitimate Interest)
- **IP Addresses**: Collected for security monitoring and bot detection. IP addresses are anonymized after initial processing where possible.
- **User Agent Strings**: Used to identify potential bot behavior and malicious actors.
- **Request Headers**: Minimal headers necessary for security analysis.
- **Access Logs**: Timestamps and requested URLs for security monitoring.

### Optional Data (Legal Basis: Consent)
- **Analytics Data**: Usage patterns and system performance metrics (requires consent).
- **Behavioral Data**: Advanced bot detection patterns (requires consent).

## Legal Basis for Processing

We process personal data under the following legal bases:
1. **Legitimate Interest**: Security monitoring and protection against malicious actors
2. **Consent**: Optional analytics and advanced behavioral analysis
3. **Legal Obligation**: Compliance with applicable cybersecurity laws

## Data Minimization

We implement data minimization principles:
- IP addresses are truncated to reduce precision (e.g., last octet removed)
- Only essential request headers are stored
- User agent strings are truncated to 100 characters
- Data is automatically deleted after the retention period

## Your Rights Under GDPR

You have the following rights regarding your personal data:

### 1. Right of Access
Request a copy of the personal data we hold about you.

### 2. Right to Rectification
Request correction of inaccurate personal data.

### 3. Right to Erasure ("Right to be Forgotten")
Request deletion of your personal data. Contact the DPO or use the Admin UI deletion request feature.

### 4. Right to Restrict Processing
Request limitation of how we process your data.

### 5. Right to Data Portability
Receive your personal data in a structured, machine-readable format.

### 6. Right to Object
Object to processing of your personal data based on legitimate interests.

### 7. Right to Withdraw Consent
Withdraw previously given consent at any time.

### 8. Right to Lodge a Complaint
File a complaint with your local data protection authority.

## Data Retention

Personal data is retained for:
- **Default Period**: 365 days (configurable via `GDPR_DATA_RETENTION_DAYS`)
- **Security Logs**: As required by applicable laws
- **Audit Logs**: Retained for compliance purposes

Data is automatically deleted after the retention period expires.

## Data Sharing

- **Internal Use Only**: Logs and data are used solely for security analysis
- **No Third-Party Sales**: We do not sell or rent any personal data
- **Community Blocklists**: IP addresses of confirmed malicious actors may be shared with community blocklists (with explicit consent where required)
- **Legal Requirements**: Data may be disclosed if required by law

## Consent Management

For non-essential data processing, we maintain a consent management system:
- Explicit consent is required before processing optional data
- Consent can be withdrawn at any time
- Consent records are maintained with timestamps and IP addresses

## Security Measures

We implement appropriate technical and organizational measures:
- Encryption in transit and at rest
- Access controls and authentication
- Regular security audits
- Audit logging of all data access

## Data Protection Impact Assessment (DPIA)

We conduct regular privacy impact assessments to:
- Identify and minimize data protection risks
- Ensure compliance with GDPR requirements
- Document processing activities
- Review and update security measures

## Automated Decision-Making

This system uses automated bot detection and classification. Automated decisions may result in:
- Rate limiting or blocking of suspicious traffic
- CAPTCHA challenges
- IP address blacklisting

You have the right to contest automated decisions and request human review.

## International Data Transfers

If data is transferred outside the EU/EEA:
- Appropriate safeguards are implemented (e.g., Standard Contractual Clauses)
- Transfers comply with GDPR Chapter V requirements

## Contact Information

For privacy-related questions or to exercise your rights:
- Email: See `GDPR_DPO_EMAIL` configuration
- Submit a data deletion request via the Admin UI
- Contact your local data protection authority

## Changes to This Policy

We may update this privacy policy periodically. Changes will be reflected in the "Last Updated" date at the top of this document.

## Compliance

This system is designed to comply with:
- General Data Protection Regulation (GDPR) - EU Regulation 2016/679
- ePrivacy Directive
- Applicable national data protection laws

For technical details on GDPR implementation, see `docs/legal_compliance.md`.
