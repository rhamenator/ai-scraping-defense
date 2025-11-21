FROM python:3.10-slim

# Container runtime security: Add security labels
LABEL org.opencontainers.image.security.capabilities="drop_all" \
      org.opencontainers.image.security.read_only_root_filesystem="true" \
      org.opencontainers.image.security.no_new_privileges="true" \
      org.opencontainers.image.vendor="AI Scraping Defense" \
      org.opencontainers.image.description="Prompt Router with runtime security hardening"

WORKDIR /app

# Create non-root user for runtime security
RUN groupadd -r promptrouter && useradd -r -g promptrouter promptrouter && \
    mkdir -p /app/tmp /app/cache && \
    chown -R promptrouter:promptrouter /app

COPY --chown=promptrouter:promptrouter . .

RUN pip install --no-cache-dir fastapi uvicorn httpx cachetools prometheus-client

USER promptrouter

# Runtime should enforce: --security-opt=no-new-privileges:true --cap-drop=ALL --read-only
# Allow overriding the exposed port using the PORT env var
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8009}"]
