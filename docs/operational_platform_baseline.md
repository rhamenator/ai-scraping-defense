# Operational Platform Baseline

This document defines the current operational-platform baseline for the AI Scraping Defense Stack.

## Goals

The baseline exists to keep day-two operations:

- consistent across preview, staging, and release paths
- observable enough for operators to understand service health and ownership
- grounded in the deployment workflows the repository actually supports today
- explicit about which practices are required versus still aspirational

## Current Supported Platform Surface

The current operational platform surface is built around:

- repository-driven image builds and release publication
- preview, staging, and production environment flows
- containerized deployment through Compose and Kubernetes
- observability through shared `/health`, `/metrics`, logs, and dashboards
- documented operator procedures for backup, recovery, and incident handling

## Operational Ownership Expectations

The baseline expects operators to have a clear owner for:

- public ingress and DNS
- container image publication and deployment rollout
- Redis, PostgreSQL, and persistent backup handling
- metrics, logs, and alert routing
- incident response and rollback decisions

This repo documents the technical paths, but it does not assign those owners on behalf of the deploying organization.

## Deployment and Environment Rules

Operational platform changes should preserve:

- the documented preview and environment model in [environments-and-previews.md](environments-and-previews.md)
- the supported deployment assumptions in [cloud_provider_deployment.md](cloud_provider_deployment.md)
- the monitoring and observability surface in [monitoring_stack.md](monitoring_stack.md)
- the operator workflows in [operations_playbooks.md](operations_playbooks.md) and [disaster_recovery.md](disaster_recovery.md)

If a change alters one of those paths, the matching docs should change in the same pull request.

## Minimum Operational Evidence

Changes that affect the operational platform should ship with:

- updated environment or deployment docs
- updated health, metrics, or operator notes when runtime behavior changes
- rollback or recovery guidance when storage, routing, or background jobs are affected
- release-checklist coverage for the changed operational path

## Non-Goals

This baseline does not require a full service catalog product, formal platform team structure, or mandatory GitOps controller for every deployment. It defines the minimum operational platform contract the current repository supports today.
