FROM openresty/openresty:alpine

# Container runtime security: Add security labels
LABEL org.opencontainers.image.security.capabilities="drop_all" \
      org.opencontainers.image.security.read_only_root_filesystem="true" \
      org.opencontainers.image.security.no_new_privileges="true" \
      org.opencontainers.image.vendor="AI Scraping Defense" \
      org.opencontainers.image.description="OpenResty Proxy with runtime security hardening"

# Create required directories with correct permissions
RUN mkdir -p /usr/local/openresty/nginx/logs \
    && chown -R nobody:nobody /usr/local/openresty/nginx/logs \
    && mkdir -p /var/run/openresty \
    && chown -R nobody:nobody /var/run/openresty \
    && mkdir -p /tmp/nginx /var/cache/nginx \
    && chown -R nobody:nobody /tmp/nginx /var/cache/nginx

# Update nginx.conf to use the correct pid path
RUN sed -i 's|pid.*|pid /var/run/openresty/nginx.pid;|' /usr/local/openresty/nginx/conf/nginx.conf

# Switch to non-root user
USER nobody

# Runtime should enforce: --security-opt=no-new-privileges:true --cap-drop=ALL --read-only
# With tmpfs mounts for: /tmp/nginx, /var/cache/nginx, /usr/local/openresty/nginx/logs