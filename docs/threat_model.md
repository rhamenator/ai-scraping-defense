# Threat Model

This document outlines the primary threats considered when deploying the AI Scraping Defense stack.

## Goals
- Prevent large-scale scraping of FOSS and documentation sites.
- Detect malicious automation without harming legitimate users.

## Threats
- **Automated Web Scrapers:** Bots that harvest site content without permission.
- **Malicious Probing:** Attackers scanning for exploitable vulnerabilities.
- **Credential Stuffing:** Attempts to reuse leaked credentials against login forms.
- **Evasive Bots:** Tools that rotate IPs or user agents to bypass simple filters.

## Assets
- **Request telemetry** (logs, metrics, audit trails)
- **Blocklists and escalation decisions**
- **Admin UI credentials and WebAuthn metadata**
- **Secrets and API keys**
- **Training corpora and models**

## Entry Points
- **Nginx ingress** (public HTTP/S)
- **AI webhook** (`/webhook`)
- **Admin UI** (basic auth + 2FA/WebAuthn)
- **Redis/Postgres** (internal network)
- **Prometheus metrics endpoints**

## Trust Boundaries
- Internet → Nginx ingress
- Nginx ingress → internal services
- Admin UI → Redis/Postgres
- External dependencies → alerting/webhook integrations

## Assumptions
- Internal service-to-service traffic is on a trusted network segment.
- Secrets are stored in a secret manager or mounted read-only.
- TLS is terminated at ingress and internal communication is restricted.

## Abuse Cases
- **Bypass rate limits** via distributed IPs or headless browsers.
- **Exploit webhook endpoints** to trigger false positives or DoS.
- **Privilege escalation** through misconfigured admin credentials.
- **Data exfiltration** via misrouted alert/webhook callbacks.

## Mitigations
- Rate limiting, WAF rules, and tarpit endpoints for scraper traffic.
- SSRF protections and allowlists on outbound requests.
- MFA/WebAuthn for admin workflows and backup code rotation.
- Security scans, audits, and dependency management in CI.

## Out of Scope
- Protection against targeted exploitation of unrelated backend services.
