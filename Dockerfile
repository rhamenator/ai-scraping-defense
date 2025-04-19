# Dockerfile for AI Scraping Defense Stack
# Base image with common dependencies

FROM ubuntu:22.04

# Avoid prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# --- System Dependencies ---
# Install NGINX, Lua module, Python, GoAccess, Fail2ban, Redis client, and essential tools
RUN apt-get update && apt-get install -y \
    nginx \
    # --- NGINX Lua Modules ---
    lua-nginx-module \
    libnginx-mod-http-lua \
    # --- Lua Redis Client (for blocklist check) ---
    lua-resty-redis \
    # --- Other Dependencies ---
    fail2ban \
    goaccess \
    python3 \
    python3-pip \
    python3-venv \
    python-is-python3 \
    curl \
    git \
    build-essential \
    jq \
    redis-tools \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

    

# --- Python Setup ---
# Copy base requirements first for layer caching
COPY requirements.txt /app/requirements.txt

# Create a virtual environment and install base Python packages
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# --- Directory Structure ---
RUN mkdir -p /etc/nginx/lua /var/www/html/docs /app/tarpit /app/escalation /app/admin_ui /app/rag /app/shared /app/ai_service /logs /archives

# --- NGINX Configuration ---
COPY nginx/nginx.conf /etc/nginx/nginx.conf
# Copies detect_bot.lua and check_blocklist.lua to the NGINX Lua directory
COPY nginx/lua /etc/nginx/lua

# --- GoAccess Configuration ---
COPY goaccess/goaccess.conf /etc/goaccess/goaccess.conf

# --- Application Code ---
# Copy individual service directories (will be built separately in docker-compose)
# Note: Ensure these directories exist at the build context root
COPY tarpit /app/tarpit
COPY escalation /app/escalation
COPY admin_ui /app/admin_ui
COPY rag /app/rag
COPY shared /app/shared
COPY ai_service /app/ai_service
COPY metrics.py /app/ 

# --- Static Documentation ---
COPY docs /var/www/html/docs

# --- Entrypoint ---
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# --- Expose Ports ---
EXPOSE 80

# --- Set Entrypoint ---
ENTRYPOINT ["docker-entrypoint.sh"]

# Base CMD (can be overridden by docker-compose)
CMD ["nginx", "-g", "daemon off;"]