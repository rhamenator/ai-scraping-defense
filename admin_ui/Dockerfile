# syntax=docker/dockerfile:1

# --- Base image ---
FROM python:3.11-slim AS base

# --- Builder stage: install dependencies in a venv ---
FROM base AS builder
WORKDIR /app

# Install build dependencies (if any needed for pip install)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt first for better cache usage
COPY --link requirements.txt ./

# Create venv and install dependencies using pip cache
RUN python -m venv .venv \
    && .venv/bin/pip install --upgrade pip \
    && --mount=type=cache,target=/root/.cache/pip \
       .venv/bin/pip install -r requirements.txt

# --- Final stage ---
FROM base AS final

# Create non-root user
RUN useradd -m --uid 1000 adminui

WORKDIR /app

# Copy venv from builder
COPY --from=builder /app/.venv .venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code (admin_ui and templates)
COPY --link admin_ui/ ./admin_ui/

# Expose Flask port
EXPOSE 5002

# Switch to non-root user
USER adminui

# Entrypoint
CMD ["python", "-m", "admin_ui.admin_ui"]
