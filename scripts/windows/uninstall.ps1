param(
    [switch]$PurgeData,
    [switch]$RemoveImages,
    [switch]$RestartCommonWebServices
)

$ErrorActionPreference = 'Stop'
$RootDir = Split-Path -Parent $PSScriptRoot
. "$PSScriptRoot/Lib.ps1"
Set-Location -Path $RootDir

$args = @('down','--remove-orphans')
if ($PurgeData) {
    $args += '--volumes'
}
Invoke-Compose -Args $args

if ($RemoveImages) {
    docker image rm `
        ai-scraping-defense-ai_service `
        ai-scraping-defense-admin_ui `
        ai-scraping-defense-escalation_engine `
        ai-scraping-defense-tarpit_api *> $null
}

if ($RestartCommonWebServices) {
    foreach ($svc in @('W3SVC','nginx','apache2','apache')) {
        $service = Get-Service -Name $svc -ErrorAction SilentlyContinue
        if ($service -and $service.Status -ne 'Running') {
            Start-Service -Name $svc -ErrorAction SilentlyContinue
        }
    }
}

Write-Host 'Windows uninstall complete.' -ForegroundColor Green
