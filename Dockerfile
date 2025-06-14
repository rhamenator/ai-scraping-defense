# Dockerfile for AI Scraping Defense Stack
FROM ubuntu:22.04
FROM openresty/openresty:alpine

ENV DEBIAN_FRONTEND=noninteractive

# --- System Dependencies and OpenResty Installation ---
RUN apk update && apk install -y \
    curl \
    gnupg \
    dos2unix \
    dnsutils \
    fail2ban \
    goaccess \
    python3 \
    python3-pip \
    python3-venv \
    python-is-python3 \
    git \
    build-essential \
    jq \
    redis-tools \
    && curl -fsSL https://openresty.org/package/pubkey.gpg | gpg --dearmor -o /usr/share/keyrings/openresty-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/openresty-archive-keyring.gpg] http://openresty.org/package/ubuntu jammy main" | tee /etc/apt/sources.list.d/openresty.list \
    && apk update && apk install -y openresty \
    && apk clean && rm -rf /var/lib/apt/lists/*

ENV PATH="/usr/local/openresty/nginx/sbin:/opt/venv/bin:${PATH}"

# --- Python Setup ---
COPY requirements.txt /app/requirements.txt
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r /app/requirements.txt

# --- Directory Structure ---
RUN mkdir -p /etc/nginx/lua /var/www/html/docs /app/tarpit /app/escalation /app/admin_ui /app/rag /app/shared /app/ai_service /logs /archives /etc/nginx/secrets

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
EXPOSE 80
EXPOSE 443

# --- Default Command ---
CMD ["/usr/local/openresty/nginx/sbin/nginx", "-g", "daemon off;"]
