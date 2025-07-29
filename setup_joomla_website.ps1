# This script adds Joomla and its database service to the docker-compose.yaml file.

$composeFile = "docker-compose.yaml"

# Check if docker-compose.yaml exists
if (-not (Test-Path $composeFile)) {
    Write-Host "docker-compose.yaml not found! Please run this script from the project root." -ForegroundColor Red
    exit 1
}

Write-Host "Adding Joomla services to docker-compose.yaml..."

# Define the YAML content to append using a PowerShell here-string
$joomlaServices = @"

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
      JOOMLA_DB_PASSWORD: `$`{JOOMLA_DB_PASSWORD:-changeme}
      JOOMLA_DB_NAME: joomla_db
    restart: unless-stopped

  joomla_db:
    image: mysql:8.0
    container_name: joomla_db
    environment:
      MYSQL_ROOT_PASSWORD: `$`{JOOMLA_DB_ROOT_PASSWORD:-changemeroot}
      MYSQL_USER: joomla_user
      MYSQL_PASSWORD: `$`{JOOMLA_DB_PASSWORD:-changeme}
      MYSQL_DATABASE: joomla_db
    volumes:
      - joomla_db_data:/var/lib/mysql
    networks:
      - default
    restart: unless-stopped

volumes:
  joomla_db_data:
"@

# Append the content to the docker-compose file
Add-Content -Path $composeFile -Value $joomlaServices

Write-Host "Joomla services added." -ForegroundColor Green
Write-Host "Please create a file 'nginx/sites-enabled/joomla.conf' and configure it to proxy to 'http://joomla_app:80'."
Write-Host "Then, run 'docker-compose up -d --build' to start your new Joomla site."
