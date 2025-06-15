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
    lapack-dev \
    gfortran \
    cmake \
    ninja \
    perl \
    perl-utils \
    perl-dev \
    wget \
    && rm -rf /var/cache/apk/*

# Install OpenResty packages
RUN wget https://raw.githubusercontent.com/openresty/lua-resty-redis/master/lib/resty/redis.lua -O /usr/local/openresty/lualib/resty/redis.lua && \
    wget https://raw.githubusercontent.com/pintsized/lua-resty-http/master/lib/resty/http.lua -O /usr/local/openresty/lualib/resty/http.lua && \
    wget https://raw.githubusercontent.com/pintsized/lua-resty-http/master/lib/resty/http_headers.lua -O /usr/local/openresty/lualib/resty/http_headers.lua && \
    wget https://raw.githubusercontent.com/pintsized/lua-resty-http/master/lib/resty/http_connect.lua -O /usr/local/openresty/lualib/resty/http_connect.lua

# Set environment variables
ENV PATH="/usr/local/openresty/nginx/sbin:/opt/venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1
ENV PYTORCH_ENABLE_MPS_FALLBACK=1
ENV GRPC_PYTHON_BUILD_SYSTEM_OPENSSL=1
ENV GRPC_PYTHON_BUILD_WITH_CYTHON=1
ENV MAX_JOBS=4
# Add OpenResty paths
ENV LUA_PATH="/usr/local/openresty/site/lualib/?.lua;/usr/local/openresty/lualib/?.lua;/usr/local/openresty/nginx/lua/?.lua;/etc/nginx/lua/?.lua;;"
ENV LUA_CPATH="/usr/local/openresty/site/lualib/?.so;/usr/local/openresty/lualib/?.so;;"

# --- Python Setup ---
COPY requirements.txt constraints.txt /app/

# Create and activate virtual environment
RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install wheel setuptools

# Install packages in the correct order
RUN /opt/venv/bin/pip install --no-cache-dir numpy && \
    /opt/venv/bin/pip install --no-cache-dir -r /app/constraints.txt && \
    /opt/venv/bin/pip install --no-cache-dir -r /app/requirements.txt

# Ensure venv bin directory is in PATH
ENV PATH="/opt/venv/bin:$PATH"

# Create required nginx directories with proper permissions
# [Previous content remains the same until the nginx directories section]

# Create required nginx directories with proper permissions
RUN mkdir -p \
    /var/run/openresty \
    /var/run/openresty/nginx-client-body \
    /var/cache/nginx \
    /var/cache/nginx/proxy_temp \
    /var/cache/nginx/fastcgi_temp \
    /var/cache/nginx/uwsgi_temp \
    /var/cache/nginx/scgi_temp \
    /var/log/nginx \
    /var/run/nginx \
    && chown -R nobody:nobody \
        /var/run/openresty \
        /var/run/openresty/nginx-client-body \
        /var/cache/nginx \
        /var/cache/nginx/proxy_temp \
        /var/cache/nginx/fastcgi_temp \
        /var/cache/nginx/uwsgi_temp \
        /var/cache/nginx/scgi_temp \
        /var/log/nginx \
        /var/run/nginx \
        /usr/local/openresty/nginx \  
        /usr/local/openresty/nginx/logs \  
    && chmod 755 /var/run/openresty \
    && chmod 700 /var/run/openresty/nginx-client-body \
    && chmod -R 755 /var/cache/nginx \
    && chmod -R 755 /usr/local/openresty/nginx/logs

# --- Directory Structure ---
RUN mkdir -p \
    /etc/nginx/lua \
    /var/www/html/docs \
    /app/tarpit \
    /app/escalation \
    /app/admin_ui \
    /app/rag \
    /app/shared \
    /app/ai_service \
    /logs \
    /archives \
    /etc/nginx/secrets \
    && chown -R nobody:nobody \
        /etc/nginx/lua \
        /var/www/html/docs \
        /app \
        /logs \
        /archives \
        /etc/nginx/secrets

# --- Configuration Files ---
COPY nginx/nginx.conf /etc/nginx/nginx.conf

# Update nginx.conf to use the correct pid path
RUN sed -i 's|pid.*|pid /var/run/openresty/nginx.pid;|' /etc/nginx/nginx.conf && \
    touch /var/run/openresty/nginx.pid && \
    chown nobody:nobody /var/run/openresty/nginx.pid

COPY nginx/lua /etc/nginx/lua
COPY goaccess/goaccess.conf /etc/goaccess/goaccess.conf

# Set proper permissions for Lua scripts and modules
RUN chmod -R 755 /etc/nginx/lua /usr/local/openresty/lualib/resty && \
    chown -R nobody:nobody /etc/nginx/lua /usr/local/openresty/lualib/resty

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

# Switch to non-root user
USER nobody

# --- Default Command ---
CMD ["/usr/local/openresty/nginx/sbin/nginx", "-g", "daemon off;"]