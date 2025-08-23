# Attach WordPress after quick_takeover
# Assumes quick_takeover has already launched the AI Scraping Defense stack.
param()
$ErrorActionPreference = 'Stop'
$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location -Path $RootDir

Write-Host "=== Attaching WordPress after quick_takeover ===" -ForegroundColor Cyan

# Update REAL_BACKEND_HOST
$content = Get-Content '.env'
if ($content -match '^REAL_BACKEND_HOST=') {
    $content = $content -replace '^REAL_BACKEND_HOST=.*', 'REAL_BACKEND_HOST=http://wordpress:80'
    $content | Set-Content '.env'
} else {
    Add-Content '.env' 'REAL_BACKEND_HOST=http://wordpress:80'
}

$networkName = (docker network ls --filter name=defense_network -q | Select-Object -First 1)
if (-not $networkName) {
    Write-Error 'Could not locate the defense_network. Did quick_takeover run?'
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
