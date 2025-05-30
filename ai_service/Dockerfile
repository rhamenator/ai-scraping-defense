# syntax=docker/dockerfile:1

# --- Base image ---
FROM python:3.11-slim AS base

# Set working directory
WORKDIR /app

# --- Builder stage ---
FROM base AS builder

# System dependencies for ai_service (if any needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt with bind mount for caching
COPY --link ../requirements.txt ./requirements.txt

# Create venv and install dependencies using pip cache
RUN python -m venv /app/.venv \
    && ./.venv/bin/pip install --upgrade pip \
    && --mount=type=cache,target=/root/.cache/pip \
       ./.venv/bin/pip install -r requirements.txt

# --- Final stage ---
FROM base AS final

# Create non-root user
RUN useradd -m aiuser

WORKDIR /app

# Copy only the ai_service code
COPY --link . ./ai_service

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Set environment to use venv
ENV PATH="/app/.venv/bin:$PATH"

# Expose FastAPI port
EXPOSE 8000

# Use non-root user
USER aiuser

# Entrypoint for FastAPI app
CMD ["uvicorn", "ai_service.ai_webhook:app", "--host", "0.0.0.0", "--port", "8000"]
