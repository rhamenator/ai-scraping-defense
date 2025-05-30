# syntax=docker/dockerfile:1

# --- Base image ---
FROM python:3.11-slim AS base

# Set working directory
WORKDIR /app

# --- Builder stage ---
FROM base AS builder

# Install build dependencies (if any needed for pip installs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt with --link for layer caching
COPY --link ../requirements.txt ./requirements.txt

# Create virtual environment and install dependencies using pip cache
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m venv /app/.venv && \
    ./.venv/bin/pip install --upgrade pip && \
    ./.venv/bin/pip install -r requirements.txt

# Copy the rag service code (only) with --link
COPY --link . ./rag

# --- Final stage ---
FROM base AS final

# Create a non-root user
RUN useradd -m raguser
USER raguser

WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy the rag service code from builder
COPY --from=builder /app/rag /app/rag

# Set environment to use the venv
ENV PATH="/app/.venv/bin:$PATH"

# Default command (can be overridden)
CMD ["python", "-m", "rag.training"]

# Expose no ports by default (scripts are batch jobs)
# EXPOSE 8000

# Notes:
# - Do NOT copy .env, secrets, .git, or any sensitive files (should be in .dockerignore)
# - Use environment variables for DB credentials and other secrets at runtime
