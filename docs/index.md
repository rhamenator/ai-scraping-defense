# AI Scraping Defense Stack

Welcome to the official documentation for the **AI Scraping Defense Stack** — a modular, containerized system for detecting and deterring AI-based web scrapers, bots, and unauthorized data miners.

## 🚀 Overview

This project includes:

- ✅ FastAPI-based tarpit to delay or confuse bots
- 🔄 ZIP archive honeypots containing fake JavaScript traps
- 🧠 Escalation engine for behavioral analysis (local + LLM)
- 📊 Admin UI with real-time metrics
- 📝 Markov-based fake text generators
- 📈 Lua/NGINX filtering and GoAccess log reporting
- 🛡️ Fail2Ban compatibility and webhook alerts

> This stack is modular, extensible, and designed for privacy-conscious and resource-constrained FOSS projects.

---

## 📚 Documentation

### 🧭 Architecture

- [System Overview](architecture.md)

### 💻 API Reference

- [Endpoint Reference](api_reference.md)

### 🛠 Microservice Details

- [`tarpit/README.md`](../tarpit/README.md)

---

## ⚖️ Legal & Compliance

- [License Summary](../LICENSE.md)
- [Third-Party Licenses](../third_party_licenses.md)
- [Privacy Policy](privacy_policy.md)
- [Security Disclosure Policy](../SECURITY.md)
- [Compliance Checklist](legal_compliance.md)

---

## 🤝 Contributing

- [How to Contribute](../CONTRIBUTING.md)
- [Changelog](../CHANGELOG.md)
- [Code of Conduct](code_of_conduct.md)

We welcome pull requests, discussion, and suggestions from the security, web performance, FOSS, and ethical AI communities.

---

## 📦 Deployment

### Using Docker Compose (Recommended for Development/Testing)

See the [Getting Started Guide](getting_started.md).

### Using Kubernetes (Recommended for Production)

See the [Kubernetes Deployment Guide](kubernetes_deployment.md).

---

## 🔗 System Components

- Tarpit API Documentation
- Escalation Engine
- Admin UI
- RAG + Heuristic Logic
- ZIP Honeypot System

📈 Monitoring
Navigate to:
Admin UI → [http://localhost/admin/](http://localhost/admin/)
Metrics API → [http://localhost/admin/metrics](http://localhost/admin/metrics)

💡 Learn More
Visit the GitHub repository or explore Discussions to ask questions or suggest features.

📢 Feedback & Security
To report bugs or vulnerabilities, see our Security Policy. For general discussion, use the Discussions tab on GitHub.

This documentation is automatically published via GitHub Pages from the /docs directory.
