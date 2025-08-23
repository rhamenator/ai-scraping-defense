# Requires Docker Desktop
param()
$adminCheck = [Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $adminCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "It's recommended to run this script from an elevated PowerShell session."
}
$ErrorActionPreference = 'Stop'
Write-Host "=== Launching WordPress Site ===" -ForegroundColor Cyan

if (-not (Test-Path '.env')) {
    Copy-Item 'sample.env' '.env'
    Write-Host 'Created .env from sample.env'
}

# Update REAL_BACKEND_HOST
$content = Get-Content '.env'
if ($content -match '^REAL_BACKEND_HOST=') {
    $content = $content -replace '^REAL_BACKEND_HOST=.*', 'REAL_BACKEND_HOST=http://wordpress:80'
    $content | Set-Content '.env'
} else {
    Add-Content '.env' 'REAL_BACKEND_HOST=http://wordpress:80'
}

# Start the stack
docker-compose up --build -d

$networkName = (docker network ls --filter name=defense_network -q | Select-Object -First 1)
if (-not $networkName) {
    Write-Error 'Could not locate the defense_network. Is the stack running?'
    exit 1
}

# Launch MariaDB
if (-not (docker ps -q -f name=wordpress_db)) {
    docker run -d --name wordpress_db `
        --network $networkName `
        -e MYSQL_ROOT_PASSWORD=example `
        -e MYSQL_DATABASE=wordpress `
        -e MYSQL_USER=wordpress `
        -e MYSQL_PASSWORD=wordpress `
        mariadb:10
} else {
    Write-Host 'wordpress_db container already running'
}

# Launch WordPress
if (-not (docker ps -q -f name=wordpress)) {
    docker run -d --name wordpress `
        --network $networkName `
        -p 8082:80 `
        -e WORDPRESS_DB_HOST=wordpress_db:3306 `
        -e WORDPRESS_DB_USER=wordpress `
        -e WORDPRESS_DB_PASSWORD=wordpress `
        -e WORDPRESS_DB_NAME=wordpress `
        wordpress:php8.1-apache
} else {
    Write-Host 'wordpress container already running'
}

Write-Host 'WordPress available at http://localhost:8082'
Write-Host 'Proxy via AI Scraping Defense at http://localhost:8080'
