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
    rm -rf /var/lib/apt/lists/* && \
    apt-get purge -y --auto-remove build-essential

RUN pip check

WORKDIR /app

ENV PYTHONPATH "${PYTHONPATH}:/app"

COPY requirements.txt constraints.txt ./

RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

COPY src/ /app/src/

# Copy the pre-built shared libraries from the builder stage
COPY --from=builder /build/tarpit-rs/target/release/libtarpit_rs.so /app/tarpit_rs.so
COPY --from=builder /build/frequency-rs/target/release/libfrequency_rs.so /app/frequency_rs.so
COPY --from=builder /build/markov-train-rs/target/release/libmarkov_train_rs.so /app/markov_train_rs.so

COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# The CMD or ENTRYPOINT to run the specific service will be provided
# in the docker-compose.yaml or Kubernetes manifest.