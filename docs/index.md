# AI Scraping Defense Stack

Welcome to the official documentation for the **AI Scraping Defense Stack** — a modular, containerized system for detecting and deterring AI-based web scrapers, bots, and unauthorized data miners.

## Project Goal

The project’s core objective is to establish a resilient and adaptable multi-tiered defense framework against automated threats, with a focus on advanced AI-driven web scrapers. Leveraging a microservice architecture enables efficient detection, profiling, and mitigation of hostile bot activity—while maintaining a seamless experience for genuine human users. By integrating specialized tactics such as tarpit APIs, honeypot traps, and behavioral analytics, the system safeguards web applications and alleviates operational strain on servers and server administrators.

## Overview

This project includes:

- FastAPI-based tarpit to delay or confuse bots
- ZIP archive honeypots containing fake JavaScript traps
- Auto-generated decoy API endpoints to mislead scrapers
- Escalation engine for behavioral analysis (local + LLM)
- Admin UI with real-time metrics
- Markov-based fake text generators
- Lua/NGINX filtering and GoAccess log reporting
- Fail2Ban compatibility and webhook alerts
- ✅ Anomaly Detection via AI – Move beyond heuristics and integrate anomaly detection models for more adaptive security.

> This stack is modular, extensible, and designed for privacy-conscious and resource-constrained FOSS projects.
---

## **Key Documentation Pages**

To get a full understanding of the project, please review the following documents:

- [**Getting Started**](getting_started.md)**:** The essential first step. This guide provides detailed instructions for setting up the complete development environment on your local machine using Docker Compose.  
- [**System Architecture**](architecture.md)**:** A high-level overview of the different components of the system and how they fit together. This is the best place to start to understand the overall design.  
- [**Key Data Flows**](key_data_flows.md)**:** This document explains the lifecycle of a request as it moves through our defense layers, from initial filtering to deep analysis.  
- [**Model Adapter Guide**](model_adapter_guide.md)**:** A technical deep-dive into the flexible Model Adapter pattern, which allows the system to easily switch between different machine learning models and LLM providers.  
- [**Kubernetes Deployment**](kubernetes_deployment.md)**:** A step-by-step guide for deploying the entire application stack to a production-ready Kubernetes cluster.
- [**Fail2ban**](fail2ban.md)**:** Configuration and deployment instructions for the optional firewall banning service.

---

## Legal & Compliance

- [License Summary](../LICENSE.md)
- [Third-Party Licenses](third_party_licenses.md)
- [Privacy Policy](privacy_policy.md)
- [Security Disclosure Policy](../SECURITY.md)
- [Compliance Checklist](legal_compliance.md)

---

## Contributing

- [How to Contribute](../CONTRIBUTING.md)
- [Changelog](../CHANGELOG.md)
- [Code of Conduct](code_of_conduct.md)

We welcome pull requests, discussion, and suggestions from the security, web performance, FOSS, and ethical AI communities.

---

## Learn More

Visit the GitHub repository or explore Discussions to ask questions or suggest features.

## Feedback & Security

To report bugs or vulnerabilities, see our Security Policy. For general discussion, use the Discussions tab on GitHub.

This documentation is automatically published via GitHub Pages from the /docs directory.
