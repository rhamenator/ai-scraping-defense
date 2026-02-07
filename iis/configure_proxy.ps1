# Configure-Proxy.ps1
<##
.SYNOPSIS
    Enables Application Request Routing and sets up basic reverse proxy rules in IIS.
.DESCRIPTION
    Adds URL Rewrite rules for the Admin UI and a catch-all rule that forwards
    other traffic to the backend application.
##>
param(
    [string]$SiteName = 'Default Web Site',
    [string]$BackendUrl = 'http://localhost:8080'
)

Import-Module WebAdministration

Write-Host 'Enabling ARR proxy...' -ForegroundColor Cyan
Set-WebConfigurationProperty -pspath 'MACHINE/WEBROOT/APPHOST' -filter 'system.webServer/proxy' -name 'enabled' -value 'True'

$sitePath = "MACHINE/WEBROOT/APPHOST/$SiteName"
$rulesPath = "$sitePath/system.webServer/rewrite/rules"

# Admin UI rule
if (-not (Get-WebConfigurationProperty -pspath $sitePath -filter "system.webServer/rewrite/rules/rule[@name='AdminUI']" -name 'name' -ErrorAction SilentlyContinue)) {
    Add-WebConfigurationProperty -pspath $sitePath -filter 'system.webServer/rewrite/rules' -name '.' -value @{name='AdminUI';patternSyntax='ECMAScript';stopProcessing='true';match=@{url='admin/(.*)'};action=@{type='Rewrite';url='http://localhost:5002/{R:1}'}}
}

# Catch-all backend rule
if (-not (Get-WebConfigurationProperty -pspath $sitePath -filter "system.webServer/rewrite/rules/rule[@name='BackendCatchAll']" -name 'name' -ErrorAction SilentlyContinue)) {
    Add-WebConfigurationProperty -pspath $sitePath -filter 'system.webServer/rewrite/rules' -name '.' -value @{name='BackendCatchAll';patternSyntax='ECMAScript';stopProcessing='true';match=@{url='(.*)'};action=@{type='Rewrite';url="$BackendUrl/{R:1}"}}
}

Write-Host 'Proxy rules configured.' -ForegroundColor Green
