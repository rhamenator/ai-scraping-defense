#!/usr/bin/env bash
# This script adds Joomla and its database service to the docker-compose.yaml file.

# Check if docker-compose.yaml exists
if [ ! -f docker-compose.yaml ]; then
    echo "docker-compose.yaml not found! Please run this script from the project root."
    exit 1
fi

echo "Adding Joomla services to docker-compose.yaml..."

# Append Joomla and its database service to the docker-compose file
cat <<EOT >> docker-compose.yaml

  joomla:
    image: joomla:latest
    container_name: joomla_app
    depends_on:
      - joomla_db
    networks:
      - default
    environment:
      JOOMLA_DB_HOST: joomla_db:3306
      JOOMLA_DB_USER: joomla_user
      JOOMLA_DB_PASSWORD: \${JOOMLA_DB_PASSWORD:-changeme}
      JOOMLA_DB_NAME: joomla_db
    restart: unless-stopped

  joomla_db:
    image: mysql:8.0
    container_name: joomla_db
    environment:
      MYSQL_ROOT_PASSWORD: \${JOOMLA_DB_ROOT_PASSWORD:-changemeroot}
      MYSQL_USER: joomla_user
      MYSQL_PASSWORD: \${JOOMLA_DB_PASSWORD:-changeme}
      MYSQL_DATABASE: joomla_db
    volumes:
      - joomla_db_data:/var/lib/mysql
    networks:
      - default
    restart: unless-stopped

volumes:
  joomla_db_data:

EOT

echo "Joomla services added."
echo "Please create a file 'nginx/sites-enabled/joomla.conf' and configure it to proxy to 'http://joomla_app:80'."
echo "Then, run 'docker compose up -d --build' to start your new Joomla site."
