FROM python:3.11-slim

# Add security labels
LABEL org.opencontainers.image.vendor="AI Scraping Defense" \
      org.opencontainers.image.title="Cloud Proxy Service" \
      org.opencontainers.image.description="Cloud proxy component for AI scraping defense" \
      security.tls="required" \
      security.unprivileged="true"

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Install dependencies as root
RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx cachetools prometheus-client

# Copy application files with proper ownership
COPY --chown=appuser:appuser main.py /app/main.py

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import httpx; httpx.get('http://localhost:8008/health')"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8008"]
