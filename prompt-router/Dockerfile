FROM python:3.11-slim

# Add security labels
LABEL org.opencontainers.image.vendor="AI Scraping Defense" \
      org.opencontainers.image.title="Prompt Router Service" \
      org.opencontainers.image.description="Prompt routing component for AI scraping defense" \
      security.tls="required" \
      security.unprivileged="true"

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Install dependencies as root
RUN pip install --no-cache-dir fastapi uvicorn httpx cachetools prometheus-client

# Copy application files with proper ownership
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import httpx; httpx.get('http://localhost:${PORT:-8009}/health')"]

# Allow overriding the exposed port using the PORT env var
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8009}"]
