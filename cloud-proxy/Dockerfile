FROM python:3.11-slim

# Security: Update packages and create non-root user
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -r appuser && \
    useradd -r -g appuser appuser

WORKDIR /app

# Install dependencies as root
RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx cachetools prometheus-client && \
    # Reduce image attack surface: build tooling is not needed at runtime.
    pip uninstall -y setuptools wheel || true && \
    pip check

# Copy application files with proper ownership
COPY --chown=appuser:appuser main.py /app/main.py

# Switch to non-root user
USER appuser

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8008"]
