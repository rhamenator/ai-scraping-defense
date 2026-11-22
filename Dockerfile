ARG PYTHON_VERSION=3.14
ARG RUST_VERSION=1.88
# The base images are pinned by digest. To build on another version (for example while triaging a dependency problem)
# pass the version AND the digest of that image, e.g.
#   --build-arg PYTHON_VERSION=3.13 --build-arg PYTHON_DIGEST=sha256:<digest of python:3.13-slim>
# The build fails if a version and its digest disagree, instead of quietly building on the pinned image.
ARG PYTHON_DIGEST=sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f
ARG RUST_DIGEST=sha256:af306cfa71d987911a781c37b59d7d67d934f49684058f96cf72079c3626bfe0

# --- Builder Stage: Rust + Python 3 for building Rust libraries ---
FROM rust:${RUST_VERSION}-bookworm@${RUST_DIGEST} AS builder
ARG RUST_VERSION
RUN rustc --version | grep -F "rustc ${RUST_VERSION}." >/dev/null \
    || { echo "RUST_VERSION=${RUST_VERSION} does not match the pinned builder image ($(rustc --version)); pass RUST_DIGEST for that version too" >&2; exit 1; }

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

# --- Final Stage: Python app with built Rust shared libraries ---
# FROM ubuntu:22.04
FROM python:${PYTHON_VERSION}-slim@${PYTHON_DIGEST}
ARG PYTHON_VERSION
RUN python -c "import sys; v = '%d.%d' % sys.version_info[:2]; sys.exit(0 if v == '${PYTHON_VERSION}' else 'PYTHON_VERSION=${PYTHON_VERSION} does not match the pinned image (Python ' + v + '); pass PYTHON_DIGEST for that version too')"

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
        make \
        pkg-config \
        cmake && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create a dedicated non-root user with specific UID/GID for consistency
RUN groupadd -r appuser -g 1000 && \
    useradd --create-home --home-dir /home/appuser -g appuser -u 1000 appuser

WORKDIR /app

ENV PYTHONPATH=/app/src

COPY requirements.txt constraints.txt ./

# Install dependencies as root into the image's site-packages. We still run the
# app as non-root, but avoid pip falling back to a user-install (which requires
# a writable $HOME). Remove build and environment-management tools afterward:
# their bundled wheels and vendored libraries can retain vulnerable versions.
RUN python -m pip install --no-cache-dir --upgrade "pip>=26.2.0" "setuptools>=83.0.0" && \
    pip install --no-cache-dir -r requirements.txt -c constraints.txt && \
    pip check && \
    python -m pip uninstall -y pip-tools virtualenv setuptools pip && \
    python -c "import fastapi, redis, urllib3, importlib.util; assert importlib.util.find_spec('pip') is None" && \
    rm -rf /root/.cache/pip

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
