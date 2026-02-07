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

# Security metadata
LABEL security.non-root="true" \
      security.read-only-root-fs="supported" \
      security.no-new-privileges="true"

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

# Create a dedicated non-root user with specific UID/GID for consistency
RUN groupadd -r appuser -g 1000 && \
    useradd --create-home --home-dir /home/appuser -g appuser -u 1000 appuser

WORKDIR /app

ENV PYTHONPATH "${PYTHONPATH}:/app"

COPY requirements.txt constraints.txt ./

# Install dependencies as root into the image's site-packages. We still run the
# app as non-root, but avoid pip falling back to a user-install (which requires
# a writable $HOME).
RUN python -m pip install --no-cache-dir --upgrade "pip>=26.0" && \
    pip install --no-cache-dir -r requirements.txt -c constraints.txt && \
    rm -rf /root/.cache/pip && \
    # Trivy may flag vulnerabilities in setuptools' vendored dependencies (e.g. jaraco.context).
    # We keep setuptools for build tooling included in requirements.txt (pip-tools), but remove
    # unused vendored modules to reduce exposure in the runtime image.
    python -c "import shutil; from pathlib import Path; import setuptools; vendor=Path(setuptools.__file__).parent/'_vendor'; [shutil.rmtree(p, ignore_errors=True) for p in vendor.glob('jaraco.context-*.dist-info')]; ctx=vendor/'jaraco'/'context.py'; ctx.exists() and ctx.unlink(); [shutil.rmtree(p, ignore_errors=True) for p in vendor.glob('wheel-*.dist-info')]; wh=vendor/'wheel'; wh.exists() and shutil.rmtree(wh, ignore_errors=True)" && \
    pip check

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
ENTRYPOINT ["/app/docker-entrypoint.sh"]
