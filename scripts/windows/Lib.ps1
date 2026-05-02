Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-ComposeMode {
    try { docker compose version *> $null; return 'V2' } catch {}
    if (Get-Command docker-compose -ErrorAction SilentlyContinue) { return 'V1' }
    throw 'Docker Compose not found. Install Docker Desktop or docker-compose.'
}

function Invoke-Compose {
    param([Parameter(Mandatory)][string[]]$Args)
    $mode = Get-ComposeMode
    if ($mode -eq 'V2') {
        & docker @('compose') @Args
    } else {
        & docker-compose @Args
    }
}

function Get-EnvFileValue {
    param([Parameter(Mandatory)][string]$Key, [string]$Path = '.env')
    if (-not (Test-Path $Path)) { return $null }
    $line = Get-Content $Path | Where-Object { $_ -match "^$Key=" } | Select-Object -First 1
    if (-not $line) { return $null }
    return ($line -split '=', 2)[1]
}

function Test-PortInUse {
    param([Parameter(Mandatory)][int]$Port)
    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        return $null -ne $conn
    }
    $line = netstat -ano | Select-String -Pattern "LISTENING\s+.*:$Port\s"
    return $null -ne $line
}

function Test-NginxOwnsPort {
    param(
        [Parameter(Mandatory)][int]$HostPort,
        [Parameter(Mandatory)][int]$ContainerPort
    )
    $mapped = docker ps --filter "name=^/nginx_proxy$" --format "{{.Ports}}" 2>$null
    return $mapped -match "(^|, )[^,]*:$HostPort->$ContainerPort/tcp"
}

function Ensure-NoNewPrivileges {
    if (-not [string]::IsNullOrWhiteSpace($env:NO_NEW_PRIVILEGES)) {
        return
    }

    docker run --rm --security-opt no-new-privileges:true alpine:3.20 true *> $null
    if ($LASTEXITCODE -eq 0) {
        $env:NO_NEW_PRIVILEGES = 'true'
    }
    else {
        $env:NO_NEW_PRIVILEGES = 'false'
        Write-Host 'Runtime does not support no-new-privileges:true; setting NO_NEW_PRIVILEGES=false.' -ForegroundColor Yellow
    }
}

function Get-DefenseNetwork {
    $services = 'nginx_proxy','apache_proxy','admin_ui','ai_service'
    foreach ($svc in $services) {
        $exists = docker ps -a --format '{{.Names}}' | Select-String -SimpleMatch $svc
        if ($exists) {
            $net = docker inspect $svc -f '{{range $k,$v := .NetworkSettings.Networks}}{{println $k}}{{end}}' 2>$null | Select-Object -First 1
            if ($net) { return $net }
        }
    }
    $name = docker network ls --format '{{.Name}}' | Select-String -Pattern '(^defense_network$|_defense_network$)' | Select-Object -First 1
    if ($name) { return $name.Matches.Value }
    docker network ls --format '{{.Name}}' | Select-String -SimpleMatch 'defense_network' | Select-Object -First 1 | ForEach-Object { $_.ToString() }
}

function Wait-MariaDB {
    param([Parameter(Mandatory)][string]$Container, [int]$TimeoutSeconds = 120)
    $stopwatch = [Diagnostics.Stopwatch]::StartNew()
    while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        $ok = docker exec $Container sh -lc "mysqladmin ping -h 127.0.0.1 -uroot -pexample --silent" 2>$null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 2
    }
    Write-Warning "Timeout waiting for MariaDB in $Container"
}
