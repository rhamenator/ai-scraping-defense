# syntax=docker/dockerfile:1

# --- Base image ---
FROM python:3.11-slim AS base

# --- Builder stage ---
FROM base AS builder
WORKDIR /app

# System dependencies for psycopg2, redis, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt first for better caching
COPY --link ../requirements.txt ./requirements.txt

# Create venv and install dependencies using pip cache
RUN python -m venv /app/.venv \
    && ./.venv/bin/pip install --upgrade pip \
    && --mount=type=cache,target=/root/.cache/pip \
       ./.venv/bin/pip install -r requirements.txt

# --- Final stage ---
FROM base AS final

# Create non-root user
RUN useradd -m tarpituser
USER tarpituser
WORKDIR /app

# Copy venv from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy tarpit service code
COPY --link . .

# Expose the FastAPI port
EXPOSE 8001

# Healthcheck (optional, can be set in Compose/K8s)
# HEALTHCHECK CMD curl --fail http://localhost:8001/health || exit 1

# Entrypoint: run the FastAPI app with Uvicorn
CMD ["uvicorn", "tarpit_api:app", "--host", "0.0.0.0", "--port", "8001"]
