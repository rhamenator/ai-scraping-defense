FROM python:3.11-slim

# Container runtime security: Add security labels
LABEL org.opencontainers.image.security.capabilities="drop_all" \
      org.opencontainers.image.security.read_only_root_filesystem="true" \
      org.opencontainers.image.security.no_new_privileges="true" \
      org.opencontainers.image.vendor="AI Scraping Defense" \
      org.opencontainers.image.description="Cloud Proxy with runtime security hardening"

WORKDIR /app

# Create non-root user for runtime security
RUN groupadd -r cloudproxy && useradd -r -g cloudproxy cloudproxy && \
    mkdir -p /app/tmp /app/cache && \
    chown -R cloudproxy:cloudproxy /app

RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx cachetools prometheus-client

COPY --chown=cloudproxy:cloudproxy main.py /app/main.py

USER cloudproxy

# Runtime should enforce: --security-opt=no-new-privileges:true --cap-drop=ALL --read-only
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8008"]
