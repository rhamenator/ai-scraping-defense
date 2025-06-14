# Clean up
docker-compose down
docker system prune -f

# Build and run
docker-compose build --no-cache && \
docker-compose up -d && \
docker-compose logs -f && \
docker exec nginx_proxy nginx -t && \
docker exec nginx_proxy /usr/local/openresty/luajit/bin/luajit -e "require('resty.redis')" && \
docker exec nginx_proxy /usr/local/openresty/luajit/bin/luajit -e "require('resty.http')"