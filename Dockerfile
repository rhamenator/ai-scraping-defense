# Dockerfile for AI Scraping Defense Stack
FROM openresty/openresty:alpine

# --- Add Community Repository ---
RUN echo "https://dl-cdn.alpinelinux.org/alpine/v3.18/community" >> /etc/apk/repositories

# --- System Dependencies ---
RUN apk update && apk add --no-cache \
    curl \
    gnupg \
    coreutils \
    bind-tools \
    fail2ban \
    goaccess \
    python3 \
    python3-dev \
    py3-pip \
    git \
    build-base \
    jq \
    redis \
    linux-headers \
    musl-dev \
    libffi-dev \
    openblas-dev \
    && rm -rf /var/cache/apk/*

ENV PATH="/usr/local/openresty/nginx/sbin:/opt/venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1
# Add these environment variables for PyTorch
ENV PYTORCH_ENABLE_MPS_FALLBACK=1
ENV GRPC_PYTHON_BUILD_SYSTEM_OPENSSL=1
ENV GRPC_PYTHON_BUILD_WITH_CYTHON=1

# --- Python Setup ---
COPY requirements.txt constraints.txt /app/
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install wheel setuptools \
    # Install PyTorch first
    && /opt/venv/bin/pip install --no-cache-dir -r /app/constraints.txt \
    # Then install other requirements
    && /opt/venv/bin/pip install --no-cache-dir -r /app/requirements.txt

# --- Directory Structure ---
RUN mkdir -p /etc/nginx/lua \
    /var/www/html/docs \
    /app/tarpit \
    /app/escalation \
    /app/admin_ui \
    /app/rag \
    /app/shared \
    /app/ai_service \
    /logs \
    /archives \
    /etc/nginx/secrets

# --- Configuration Files ---
COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/lua /etc/nginx/lua
COPY goaccess/goaccess.conf /etc/goaccess/goaccess.conf

# --- Application Code ---
COPY tarpit /app/tarpit
COPY escalation /app/escalation
COPY admin_ui /app/admin_ui
COPY rag /app/rag
COPY shared /app/shared
COPY ai_service /app/ai_service
COPY util /app/util
COPY metrics.py /app/

# --- Static Documentation ---
COPY docs /var/www/html/docs

# --- Expose Ports ---
EXPOSE 80 443

# --- Default Command ---
CMD ["/usr/local/openresty/nginx/sbin/nginx", "-g", "daemon off;"]