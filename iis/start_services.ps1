# Start-Services.ps1
<##
.SYNOPSIS
    Launches the core Python services for the IIS deployment.
.DESCRIPTION
    Creates the virtual environment if necessary and starts each service
    in a new PowerShell window. Ports are read from environment variables or
    default to the values in sample.env.
##>
param([switch]$NoReset)

$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path "$PSScriptRoot/.."
Set-Location $repoRoot

if (-not $NoReset) {
    & "$repoRoot/reset_venv.ps1"
}

$activate = Join-Path $repoRoot '.venv\Scripts\Activate.ps1'
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'

$services = @(
    @{ Name='AI Service';       Module='src.ai_service.ai_webhook:app';      Port=$env:AI_SERVICE_PORT     ?? 8000 },
    @{ Name='Escalation Engine';Module='src.escalation.escalation_engine:app';Port=$env:ESCALATION_ENGINE_PORT ?? 8003 },
    @{ Name='Tarpit API';       Module='src.tarpit.tarpit_api:app';          Port=$env:TARPIT_API_PORT     ?? 8001 },
    @{ Name='Admin UI';         Module='src.admin_ui.admin_ui:app';          Port=$env:ADMIN_UI_PORT       ?? 5002 }
)

foreach ($svc in $services) {
    $cmd = "& `"$activate`"; & `"$python`" -m uvicorn $($svc.Module) --host 127.0.0.1 --port $($svc.Port)"
    $args = "-NoProfile -ExecutionPolicy Bypass -Command `$cmd"
    Start-Process powershell.exe -ArgumentList $args -WindowStyle Minimized | Out-Null
    Write-Host "Started $($svc.Name) on port $($svc.Port)" -ForegroundColor Green
}

Write-Host "All services launched." -ForegroundColor Cyan
