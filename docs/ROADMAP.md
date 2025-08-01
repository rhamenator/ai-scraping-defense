# **Roadmap**

## **Current Version: v1.0 (Stable)**

The AI Scraping Defense Stack now provides a stable, containerized defense system with real-time filtering, tarpitting, behavioral analysis, and AI-driven threat assessment.

## **Short-Term Goals (Next 3-6 Months)**

These features and enhancements are prioritized for near-term development:

* ✅ **Expanded ML Heuristics** – Improve the trained ML models (RandomForest, XGBoost, Logistic Regression) for better bot detection accuracy.
* ✅ **Adaptive Rate-Limiting** – Basic per-IP rate limiting implemented via Nginx `limit_req`.
* ✅ **Improved Admin UI** – Expand dashboard analytics for better visibility into bot trends and blocked traffic.
* ✅ **Better IP Reputation Handling** – Enhance integrations with public/community blocklists for real-time threat assessment.
* ✅ **Community Blocklist Sync** – Periodically pull shared threat data and populate the local Redis blocklist.
* ✅ **Blocklist Sync Daemon** – Background process to keep the Redis blocklist up to date.
* ✅ **Automated Testing Suite** – Develop a suite of test cases to validate detection mechanisms and tarpitting responses.  
* ✅ **Refined Markov Chain Tarpit** – Optimize PostgreSQL-backed deterministic content generation for better bot engagement.

## **Mid-Term Goals (6-12 Months)**

Expanding feature sets and refining system efficiency:

* ✅ **Multi-Tenant Support** – Enable easier deployment for multiple websites and organizations.  
* ✅ **Kubernetes Scaling Enhancements** – Initial Helm chart with optional autoscaling for large clusters.
* ✅ **Plugin API for Custom Rules** – Allow user-defined filtering rules for specialized site protection needs.  
* ✅ **Expanded Honeypots** – Introduce more deceptive mechanisms like **auto-generated bad API endpoints**.
* ✅ **Anomaly Detection via AI** – Move beyond heuristics and integrate **anomaly detection models** for more adaptive security.
* ✅ **Public Community Blocklist** – Optional contributor-driven IP reputation database.

## **Long-Term Vision (Beyond 12 Months)**

Larger-scale improvements and broader adoption:

* ✅ **Federated Model for Threat Intelligence Sharing** – Establish **peer-to-peer collaboration between deployments** to exchange bot intelligence.
* ✅ **Cloud-Based Management Dashboard** – Provide **hosted real-time monitoring** for multiple installations.
* **Industry Partnerships** – Integrate with cybersecurity initiatives and FOSS security groups for wider adoption.  
* ✅ **Automated Configuration Recommendations** – AI-driven suggestions for optimal firewall/tarpit settings based on incoming traffic patterns.
* ✅ **Optional Cloud Integrations** – Newly implemented toggles for CDN caching, DDoS mitigation, managed TLS, and WAF features.

## **How to Contribute**

If you're interested in contributing to one of these features, check out the open **Issues** on GitHub and follow the guidelines in `CONTRIBUTING.md`.

* **Feature Requests** – Open a new issue with your idea or enhancement request.
* **Bug Reports** – Report any issues you encounter to help improve the stack.
* **Code Contributions** – Submit pull requests for bug fixes or new features, following the coding standards outlined in `CONTRIBUTING.md`.

## Completed Roadmap Items

Listed below are recently finished tasks, ordered roughly by impact:

1. ✅ Adaptive Rate-Limiting
2. ✅ Community Blocklist Sync
3. ✅ Blocklist Sync Daemon
4. ✅ Better IP Reputation Handling
5. ✅ Automated Testing Suite
6. ✅ Refined Markov Chain Tarpit
7. ✅ Plugin API for Custom Rules
8. ✅ Optional Cloud Integrations
