# **Docker Strategy**

This project leverages Docker for containerization, ensuring a consistent and reproducible environment for both local development and production deployment. Our strategy has been refactored to follow modern best practices.

## **The Core Principle: A Single Base Image**

Instead of creating a separate, complex Dockerfile for each microservice, we use a single Dockerfile located in the root of the project. Python services share this root Dockerfile, while separate Dockerfiles reside in `proxy/`, `cloud-proxy/`, and `prompt-router`.

**File:** Dockerfile

This file's only responsibility is to create a lean, optimized base image for all Python services. It performs the following steps:

1. Starts from the official python:3.11-slim image.
2. Sets up the working directory and PYTHONPATH.
3. Copies and installs all dependencies from requirements.txt.
4. Copies the entire src/ directory into the image.
5. Copies the scripts/linux/docker-entrypoint.sh script for services that need it.

This approach significantly reduces build times and ensures that all Python services run in an identical, consistent environment.

## **Local Development with Docker Compose**

For local development, we use docker-compose.yaml to orchestrate the entire application stack.

**File:** docker-compose.yaml

Key features of our Docker Compose setup:

* **Service Definitions:** Each microservice (e.g., ai\_service, escalation\_engine), data store (redis, postgres), and third-party tool (mailhog) is defined as a service.
* **Image Reusability:** All Python services use the same build configuration, pointing to the root Dockerfile. The specific application to run is determined by the command key for each service.
* **Configuration via .env:** The compose file is kept clean by loading all environment variables (ports, passwords, API keys) from a .env file. This separates configuration from orchestration.
* **Live Reloading:** The volumes key is used to mount the local src directory directly into the containers (./src:/app/src). This allows you to edit your Python code on your host machine and see the changes immediately without rebuilding the image.

## **Production Deployment**

While Docker Compose is used for development, the ultimate goal is deployment to a container orchestrator like Kubernetes. The Docker image built by the root Dockerfile is platform-agnostic and can be pushed to any container registry (Docker Hub, GHCR, etc.) for use in production Kubernetes manifests.
