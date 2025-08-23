<#
.SYNOPSIS
    Runs a simple k6 stress test against the stack.
.DESCRIPTION
    Generates a temporary k6 script that repeatedly hits the target URL.
    Use only against systems you own or are authorized to test.
.PARAMETER Target
    Base URL of the stack. Default http://localhost:8080
.PARAMETER VUs
    Number of virtual users. Default 50.
.PARAMETER DurationSeconds
    Duration of the test in seconds. Default 30.
#>
param(
    [string]$Target = "http://localhost:8080",
    [int]$VUs = 50,
    [int]$DurationSeconds = 30
)
$adminCheck = [Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $adminCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "It's recommended to run this script from an elevated PowerShell session."
}

$ErrorActionPreference = 'Stop'
Write-Host '=== AI Scraping Defense: Stress Test ===' -ForegroundColor Cyan

if (-not (Get-Command k6 -ErrorAction SilentlyContinue)) {
    Write-Error 'k6 is not installed. Install it from https://k6.io/ or via Chocolatey: choco install k6'
    exit 1
}

$tempFile = New-TemporaryFile
@"
import http from 'k6/http';
import { sleep } from 'k6';

export let options = {
    vus: $VUs,
    duration: '${DurationSeconds}s',
};

export default function () {
    http.get('$Target');
    sleep(1);
}
"@ | Set-Content $tempFile -Encoding ascii

& k6 run $tempFile
Remove-Item $tempFile
Write-Host 'Stress test complete.' -ForegroundColor Green
