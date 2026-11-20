# AI Scraping Defense Documentation

This page is the canonical docs map for the Python stack. It intentionally avoids repeating architecture and setup walkthroughs that already live in dedicated pages.

## Start Here

- [Getting Started](getting_started.md)
- [Installer Contract](installer_contract.md)
- [Linux Installer](linux_installer.md)
- [Windows Installer](windows_installer.md)
- [macOS Installer](macos_installer.md)
- [Troubleshooting](troubleshooting.md)

## Architecture and Runtime

- [System Architecture](architecture.md)
- [Architecture Modernization Baseline](architecture_modernization_baseline.md)
- [Exploratory Architecture Roadmap](exploratory_architecture_roadmap.md)
- [Key Data Flows](key_data_flows.md)
- [Configuration](configuration.md)
- [Environment Cheat Sheet](env_cheatsheet.md)
- [Inter-Service Authentication](inter_service_auth.md)
- [API Versioning Policy](api_versioning.md)

## Operations and Deployment

- [Operations Guide](operations.md)
- [Operations Playbooks](operations_playbooks.md)
- [Python Dependency Refresh Plan](python_dependency_refresh_plan.md)
- [Exploratory Operations Roadmap](exploratory_operations_roadmap.md)
- [Observability Framework](observability.md)
- [Monitoring Stack](monitoring_stack.md)
- [Reliability and Capacity Operations Baseline](reliability_capacity_operations_baseline.md)
- [Release Checklist](release_checklist.md)
- [Release Artifacts](release_artifacts.md)
- [Operational Platform Baseline](operational_platform_baseline.md)
- [Kubernetes Deployment](kubernetes_deployment.md)
- [Ubuntu Reverse Proxy Deployment](ubuntu_reverse_proxy.md)
- [IIS Deployment Note](iis_deployment.md)

## Security and Quality

- [Threat Model](threat_model.md)
- [Security Assurance Program](security_assurance_program.md)
- [Delivery and Policy Enforcement Security Baseline](delivery_policy_enforcement_baseline.md)
- [Exploratory Advanced Cryptography Roadmap](exploratory_advanced_cryptography_roadmap.md)
- [Exploratory Low-Level Hardening Roadmap](exploratory_low_level_hardening_roadmap.md)
- [Security Program Foundations](security_program.md)
- [Supply Chain Security](security/supply_chain.md)
- [Third-Party Integration Security Baseline](third_party_integration_security_baseline.md)
- [Exploratory Engineering Culture Roadmap](exploratory_engineering_culture_roadmap.md)
- [Security Testing Guide](SECURITY_TESTING_GUIDE.md)
- [Engineering Quality Baseline](engineering_quality_baseline.md)
- [Performance Validation](performance_validation.md)

## ML and Analysis

- [Model Adapter Guide](model_adapter_guide.md)
- [Local Model Training](local_model_training.md)
- [Prompt Router](prompt_router.md)
- [Anomaly Alerting](ANOMALY_ALERTING.md)

## Legal and Project Policy

- [License](../LICENSE)
- [License Summary](license_summary.md)
- [Third-Party Licenses](third_party_licenses.md)
- [Privacy Policy](privacy_policy.md)
- [Data Protection Baseline](data_protection_baseline.md)
- [Compliance Controls Baseline](compliance_controls_baseline.md)
- [Compliance Governance and Assurance Baseline](compliance_governance_assurance_baseline.md)
- [Exploratory Compliance Roadmap](exploratory_compliance_roadmap.md)
- [Security Policy](../SECURITY.md)
- [Contributing](../CONTRIBUTING.md)
- [Code of Conduct](code_of_conduct.md)
- [Changelog](../CHANGELOG.md)

## Note on Scope

The Windows + IIS-first implementation is maintained in the separate `.NET` repository. See [IIS Deployment Note](iis_deployment.md) for the boundary and handoff.

## Historical Notes and Maintenance Data

- [Root cleanup decisions and checked consumers](root_cleanup.md)
- [Historical presentation](presentations/AI_Scraping_Defense_System_Presentation.pptx)
- [Problem map](triage/problem_file_map.json), [compliance input catalogue](triage/compliance_problems.json), and [milestone assignments](triage/issue_milestone_assignments.json)

These older working notes are retained as historical context, not current setup instructions:

- [Alert Management Summary](archive/root-notes/ALERT_MANAGEMENT_SUMMARY.md)
- [Quick Start Alert Management](archive/root-notes/QUICK_START_ALERT_MANAGEMENT.md)
- [Start Here Alert Management](archive/root-notes/START_HERE_ALERT_MANAGEMENT.md)
- [Code Scanning Issues](archive/root-notes/CODE_SCANNING_ISSUES.md)
- [Security Summary](archive/root-notes/SECURITY_SUMMARY.md)
- [Workflow Fixes Summary](archive/root-notes/WORKFLOW_FIXES_SUMMARY.md)
- [Workflow Investigation Summary](archive/root-notes/WORKFLOW_INVESTIGATION_SUMMARY.md)
- [Issues To Create](archive/root-notes/ISSUES_TO_CREATE.md)
- [Chat Relevant Playbook](archive/root-notes/CHAT_RELEVANT_PLAYBOOK.md)
- [Windows Handoff](archive/root-notes/WINDOWS_HANDOFF.md)
