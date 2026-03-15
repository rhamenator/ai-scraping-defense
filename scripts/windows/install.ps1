param(
    [ValidateSet('apache','nginx')]
    [string]$Proxy = 'nginx',
    [switch]$Takeover,
    [switch]$ForceEnv,
    [switch]$RegenerateSecrets,
    [switch]$SkipVenvReset,
    [switch]$RunTests,
    [switch]$SkipSmoke,
    [switch]$CheckIis
)

$adminCheck = [Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $adminCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "It's recommended to run this installer from an elevated PowerShell session."
}

$ErrorActionPreference = 'Stop'
$RootDir = Split-Path -Parent $PSScriptRoot
. "$PSScriptRoot/Lib.ps1"

if (-not $IsWindows) {
    Write-Error "Unsupported OS. This installer supports Windows only. Use scripts/linux/*.sh on Linux or scripts/macos/*.zsh on macOS."
    exit 1
}

function Test-SecretsInitialized {
    $envPath = Join-Path $RootDir '.env'
    if (-not (Test-Path $envPath)) { return $false }
    $hash = Get-EnvFileValue -Key 'ADMIN_UI_PASSWORD_HASH' -Path $envPath
    $pgFile = Join-Path $RootDir 'secrets\pg_password.txt'
    $redisFile = Join-Path $RootDir 'secrets\redis_password.txt'
    return (
        -not [string]::IsNullOrWhiteSpace($hash) -and
        (Test-Path $pgFile) -and ((Get-Item $pgFile).Length -gt 0) -and
        (Test-Path $redisFile) -and ((Get-Item $redisFile).Length -gt 0)
    )
}

function Test-IisPrerequisites {
    $issues = @()
    if (-not (Get-Module -ListAvailable -Name WebAdministration)) {
        $issues += 'Install IIS management tools / WebAdministration PowerShell module.'
    }
    if (-not (Get-Service -Name W3SVC -ErrorAction SilentlyContinue)) {
        $issues += 'Install IIS (World Wide Web Publishing Service / W3SVC).'
    }
    if (-not (Test-Path (Join-Path $RootDir 'iis\start_services.ps1'))) {
        $issues += 'Missing iis\start_services.ps1.'
    }
    if (-not (Test-Path (Join-Path $RootDir 'iis\configure_proxy.ps1'))) {
        $issues += 'Missing iis\configure_proxy.ps1.'
    }
    return $issues
}

function Assert-Command {
    param(
        [Parameter(Mandatory)][string]$Name,
        [string]$HelpMessage
    )
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        if ($HelpMessage) {
            throw "$Name is required. $HelpMessage"
        }
        throw "$Name is required."
    }
}

Set-Location -Path $RootDir
Write-Host '=== AI Scraping Defense: Windows Installer ===' -ForegroundColor Cyan

Assert-Command -Name docker -HelpMessage 'Install Docker Desktop and ensure it is running.'
Assert-Command -Name python -HelpMessage 'Install Python 3.10 or newer from python.org.'
Assert-Command -Name htpasswd -HelpMessage 'Install Apache tools or provide htpasswd on PATH.'

try {
    docker info *> $null
} catch {
    throw 'Docker Desktop is not reachable. Start Docker Desktop and verify docker info succeeds.'
}

$executionPolicy = Get-ExecutionPolicy -Scope CurrentUser
if ($executionPolicy -eq 'Restricted') {
    Write-Warning 'PowerShell execution policy is Restricted. Use Set-ExecutionPolicy -Scope CurrentUser RemoteSigned before rerunning scripts.'
}

if ($CheckIis) {
    $iisIssues = Test-IisPrerequisites
    if ($iisIssues.Count -eq 0) {
        Write-Host 'IIS integration prerequisites are present.' -ForegroundColor Green
    } else {
        Write-Warning ('IIS integration prerequisites are incomplete: ' + ($iisIssues -join ' '))
    }
}

if ($ForceEnv -or -not (Test-Path '.env')) {
    Copy-Item 'sample.env' '.env' -Force
    Write-Host 'Prepared .env from sample.env'
}

if (Test-Path (Join-Path $PSScriptRoot "setup_local_dirs.ps1")) {
    & "$PSScriptRoot/setup_local_dirs.ps1"
} else {
    throw 'Missing setup_local_dirs.ps1'
}

if ($RegenerateSecrets -or -not (Test-SecretsInitialized)) {
    & "$PSScriptRoot/Generate-Secrets.ps1" -UpdateEnv
} else {
    Write-Host 'Reusing existing local secrets. Pass -RegenerateSecrets to replace them.' -ForegroundColor Yellow
}

if (-not $SkipVenvReset) {
    & "$PSScriptRoot/reset_venv.ps1"
} elseif (-not (Test-Path '.venv\Scripts\python.exe')) {
    throw 'No usable .venv found. Re-run without -SkipVenvReset.'
}

& "$RootDir/.venv/Scripts/pip.exe" install -r requirements.txt -c constraints.txt
& "$RootDir/.venv/Scripts/python.exe" scripts/validate_env.py

if ($RunTests) {
    & "$RootDir/.venv/Scripts/python.exe" test/run_all_tests.py
}

Ensure-NoNewPrivileges

if ($Takeover) {
    & "$PSScriptRoot/quick_takeover.ps1" -Proxy $Proxy
} else {
    & "$PSScriptRoot/quick_proxy.ps1" -Proxy $Proxy
}

if (-not $SkipSmoke) {
    & "$PSScriptRoot/stack_smoke_test.ps1" -Proxy $Proxy
}

Write-Host ''
Write-Host 'Install complete.' -ForegroundColor Green
Write-Host "Proxy mode: $Proxy"
Write-Host 'Uninstall the stack with:' -ForegroundColor Cyan
Write-Host '  .\scripts\windows\uninstall.ps1'
if ($Takeover) {
    Write-Host 'If you stopped host web services manually, restart them after uninstall as needed (for IIS: Start-Service W3SVC).' -ForegroundColor Yellow
}
