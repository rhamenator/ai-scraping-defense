FROM openresty/openresty:alpine

# Create required directories with correct permissions
RUN mkdir -p /usr/local/openresty/nginx/logs \
    && chown -R nobody:nobody /usr/local/openresty/nginx/logs \
    && mkdir -p /var/run/openresty \
    && chown -R nobody:nobody /var/run/openresty

# Update nginx.conf to use the correct pid path
RUN sed -i 's|pid.*|pid /var/run/openresty/nginx.pid;|' /usr/local/openresty/nginx/conf/nginx.conf

# Switch to non-root user
USER nobody