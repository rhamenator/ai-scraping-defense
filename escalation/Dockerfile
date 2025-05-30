# syntax=docker/dockerfile:1

# --- Base image ---
FROM python:3.11-slim AS base

# --- Builder stage ---
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

# Copy escalation service code
COPY --link escalation/ ./escalation/

# Copy any shared code needed by escalation (metrics.py, shared/)
COPY --link metrics.py ./metrics.py
COPY --link shared/ ./shared/

# Copy config/robots.txt if needed at build time (for model loading)
COPY --link config/robots.txt ./config/robots.txt

# Copy model file if present (optional, will not fail if missing)
# If you want to build with a model, ensure it's present at build context
# Otherwise, the app will run in heuristic-only mode
COPY --link models/bot_detection_rf_model.joblib ./models/bot_detection_rf_model.joblib

# --- Final stage ---
FROM base AS final

WORKDIR /app

# Create non-root user
RUN useradd -m escalationuser
USER escalationuser

# Copy venv from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy app code and dependencies from builder
COPY --from=builder /app/escalation /app/escalation
COPY --from=builder /app/metrics.py /app/metrics.py
COPY --from=builder /app/shared /app/shared
COPY --from=builder /app/config /app/config
COPY --from=builder /app/models /app/models

# Expose the default port for the escalation engine (as per code: 8003)
EXPOSE 8003

# Healthcheck (optional, FastAPI has /health endpoint)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8003/health || exit 1

# Entrypoint: run the escalation engine with uvicorn
CMD ["uvicorn", "escalation.escalation_engine:app", "--host", "0.0.0.0", "--port", "8003", "--workers", "2"]
