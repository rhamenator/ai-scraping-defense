#!/bin/bash
set -e

# Basic entrypoint script

# Start NGINX in the background
if service nginx start; then
  echo "NGINX started successfully."
else
  echo "Failed to start NGINX." >&2
  exit 1
fi

# Optional: Start other services if needed, e.g., fail2ban
if service fail2ban start; then
  echo "Fail2Ban started successfully."
else
  echo "Failed to start Fail2Ban." >&2
fi

# Execute the command passed to the container (e.g., the CMD from Dockerfile or docker-compose)
exec "$@"