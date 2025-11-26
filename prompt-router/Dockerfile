FROM python:3.10-slim

# Security: Update packages and create non-root user
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -r appuser && \
    useradd -r -g appuser appuser

WORKDIR /app

# Install dependencies as root
RUN pip install --no-cache-dir fastapi uvicorn httpx cachetools prometheus-client

# Copy application files with proper ownership
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Allow overriding the exposed port using the PORT env var
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8009}"]
