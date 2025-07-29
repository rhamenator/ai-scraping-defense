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

## Out of Scope
- Protection against targeted exploitation of unrelated backend services.
