#!/bin/bash
# This script adds Drupal and its database service to the docker-compose.yaml file.

# Check if docker-compose.yaml exists
if [ ! -f docker-compose.yaml ]; then
    echo "docker-compose.yaml not found! Please run this script from the project root."
    exit 1
fi

echo "Adding Drupal services to docker-compose.yaml..."

# Append Drupal and its database service to the docker-compose file
cat <<EOT >> docker-compose.yaml

  drupal:
    image: drupal:latest
    container_name: drupal_app
    depends_on:
      - drupal_db
    networks:
      - default
    volumes:
      - drupal_files:/var/www/html/sites/default/files
      - drupal_modules:/var/www/html/modules
      - drupal_profiles:/var/www/html/profiles
      - drupal_themes:/var/www/html/themes
    restart: unless-stopped

  drupal_db:
    image: postgres:13
    container_name: drupal_db
    environment:
      POSTGRES_DB: drupal_db
      POSTGRES_USER: drupal_user
      POSTGRES_PASSWORD: \${DRUPAL_DB_PASSWORD:-changeme}
    volumes:
      - drupal_db_data:/var/lib/postgresql/data
    networks:
      - default
    restart: unless-stopped

volumes:
  drupal_files:
  drupal_modules:
  drupal_profiles:
  drupal_themes:
  drupal_db_data:

EOT

echo "Drupal services added."
echo "Please create a file 'nginx/sites-enabled/drupal.conf' and configure it to proxy to 'http://drupal_app:80'."
echo "Then, run 'docker-compose up -d --build' to start your new Drupal site."
