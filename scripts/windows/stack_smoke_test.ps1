param(
    [ValidateSet('apache','nginx')]
    [string]$Proxy = 'nginx'
)

$ErrorActionPreference = 'Stop'
$RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location -Path $RootDir

$python = Join-Path $RootDir '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    $python = 'python'
}

& $python scripts/installer_smoke_test.py --platform windows --proxy $Proxy
exit $LASTEXITCODE
