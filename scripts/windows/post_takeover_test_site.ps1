# Attach simple test site after quick_takeover
param()
$ErrorActionPreference = 'Stop'
$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location -Path $RootDir

Write-Host "=== Attaching test site after quick_takeover ===" -ForegroundColor Cyan

# Update REAL_BACKEND_HOST
$content = Get-Content '.env'
if ($content -match '^REAL_BACKEND_HOST=') {
    $content = $content -replace '^REAL_BACKEND_HOST=.*', 'REAL_BACKEND_HOST=http://fake_website:80'
    $content | Set-Content '.env'
} else {
    Add-Content '.env' 'REAL_BACKEND_HOST=http://fake_website:80'
}

$networkName = . "$PSScriptRoot/Lib.ps1"; Get-DefenseNetwork
if (-not $networkName) {
    Write-Error 'Could not locate the defense_network. Did quick_takeover run?'
    exit 1
}

# Create a simple test page
$siteDir = Join-Path (Get-Location) 'test_site'
if (-not (Test-Path $siteDir)) {
    New-Item -ItemType Directory -Path $siteDir | Out-Null
}
$htmlPath = Join-Path $siteDir 'index.html'
if (-not (Test-Path $htmlPath)) {
@"
<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"UTF-8\">
<title>Test Site</title>
</head>
<body>
  <h1>Hello from the Test Site!</h1>
  <p>If you see this page through the proxy, the stack is working.</p>
</body>
</html>
"@ | Set-Content $htmlPath
}

# Launch nginx container
if (-not (docker ps -q -f name=fake_website)) {
    docker run -d --name fake_website `
        --network $networkName `
        -p 8081:80 `
        -v "$siteDir:/usr/share/nginx/html:ro" `
        nginx:alpine
} else {
    Write-Host 'fake_website container already running'
}

Write-Host 'Test site available at http://localhost:8081'
Write-Host 'Proxy via AI Scraping Defense at http://localhost:8080'
