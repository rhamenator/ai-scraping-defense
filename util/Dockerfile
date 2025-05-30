# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

# Set up working directory
WORKDIR /app

# --- Builder stage ---
FROM base AS builder

# Install system dependencies for pip packages (lxml, bs4, requests, wikipedia-api)
RUN --mount=type=cache,target=/var/cache/apt \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libxml2-dev \
        libxslt1-dev \
        && rm -rf /var/lib/apt/lists/*

# Copy only requirements file(s) first for better cache utilization
COPY --link requirements.txt ./

# Create venv and install dependencies
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m venv .venv && \
    .venv/bin/pip install --upgrade pip && \
    .venv/bin/pip install -r requirements.txt

# Copy the rest of the util service code
COPY --link corpus_wikipedia_updater.py robots_fetcher.py ./

# --- Final stage ---
FROM base AS final

WORKDIR /app

# Create a non-root user
RUN useradd -m utiluser
USER utiluser

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
# Copy the util service code
COPY --from=builder /app/corpus_wikipedia_updater.py /app/robots_fetcher.py ./

# Set PATH to use the venv
ENV PATH="/app/.venv/bin:$PATH"

# Default command (can be overridden)
CMD ["python", "--version"]

# Notes:
# - requirements.txt must exist in ./util/ (add it if missing)
# - Do not copy .env, .git, or any secrets (should be in .dockerignore)
# - Entrypoint/command should be set per use-case (e.g., corpus_wikipedia_updater.py or robots_fetcher.py)
