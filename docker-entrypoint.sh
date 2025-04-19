#!/bin/bash
# Basic entrypoint script

# Start NGINX in the background
service nginx start

# Optional: Start other services if needed, e.g., fail2ban
# service fail2ban start

# Execute the command passed to the container (e.g., the CMD from Dockerfile or docker-compose)
exec "$@"