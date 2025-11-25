# --- Builder Stage: Rust + Python 3 for building Rust libraries ---
FROM rust:latest AS builder

# Install Python 3 and pip for PyO3 build scripts
RUN apt-get update && apt-get install -y python3 python3-pip

WORKDIR /build

# Copy Rust sources
COPY tarpit-rs ./tarpit-rs
COPY frequency-rs ./frequency-rs
COPY markov-train-rs ./markov-train-rs

# Build Rust libraries (assumes they are setup to build *.so files)
RUN cd tarpit-rs && cargo build --release && \
    cd ../frequency-rs && cargo build --release && \
    cd ../markov-train-rs && cargo build --release

# --- Final Stage: Python 3.11 app with built Rust shared libraries ---
# FROM ubuntu:22.04
FROM python:3.11-slim

# Update system packages and install dependencies with security upgrades
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y \
        apt-transport-https \
        ca-certificates \
        curl \
        python3-dev \
        libpq-dev \
        libxml2-dev \
        libxslt1-dev \
        libc6-dev \
        git \
        gcc \
        g++ \
        cmake && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create a dedicated non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Container runtime security: Add security labels and metadata
LABEL org.opencontainers.image.security.capabilities="drop_all" \
      org.opencontainers.image.security.read_only_root_filesystem="true" \
      org.opencontainers.image.security.no_new_privileges="true" \
      org.opencontainers.image.vendor="AI Scraping Defense" \
      org.opencontainers.image.description="AI Scraping Defense with runtime security hardening"

# Container runtime security: Create required writable directories for non-root user
RUN mkdir -p /app/logs /app/tmp /app/cache && \
    chown -R appuser:appuser /app/logs /app/tmp /app/cache

RUN pip check

WORKDIR /app

ENV PYTHONPATH "${PYTHONPATH}:/app"

COPY --chown=appuser:appuser requirements.txt constraints.txt ./

USER appuser
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt && \
    rm -rf /home/appuser/.cache/pip
COPY --chown=appuser:appuser src/ /app/src/

# Copy the pre-built shared libraries from the builder stage
COPY --chown=appuser:appuser --from=builder /build/tarpit-rs/target/release/libtarpit_rs.so /app/tarpit_rs.so
COPY --chown=appuser:appuser --from=builder /build/frequency-rs/target/release/libfrequency_rs.so /app/frequency_rs.so
COPY --chown=appuser:appuser --from=builder /build/markov-train-rs/target/release/libmarkov_train_rs.so /app/markov_train_rs.so

COPY --chown=appuser:appuser scripts/linux/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh && \
    chown -R appuser:appuser /app

# Drop privileges and set entrypoint
USER appuser

# Container runtime security: Set security options
# These should be enforced at runtime with:
# --security-opt=no-new-privileges:true
# --cap-drop=ALL
# --read-only (with tmpfs mounts for /app/logs, /app/tmp, /app/cache)
# --pids-limit=100
# --memory=2g
# --cpus=1.5

ENTRYPOINT ["/app/docker-entrypoint.sh"]
