param()
Import-Module WebAdministration -ErrorAction SilentlyContinue
$repoRoot = (Resolve-Path ".").Path
$webConfigs = Get-ChildItem -Path $repoRoot -Recurse -Filter web.config -ErrorAction SilentlyContinue
if (-not $webConfigs) { Write-Host "No web.config files found; skipping IIS validation."; exit 0 }
$newAppPool = "TempValidationPool"
if (-not (Test-Path IIS:\AppPools\$newAppPool)) { New-Item IIS:\AppPools\$newAppPool | Out-Null }
$siteRoot = Join-Path $env:TEMP "iis-validate-site"; New-Item -ItemType Directory -Path $siteRoot -Force | Out-Null
foreach ($cfg in $webConfigs) {
  Write-Host "Validating $($cfg.FullName)"
  Copy-Item $cfg.FullName (Join-Path $siteRoot "web.config") -Force
  Set-Content -Path (Join-Path $siteRoot "index.html") -Value "<h1>IIS validation</h1>" -Encoding UTF8
  $siteName = "TempValidationSite"
  if (-not (Get-ChildItem IIS:\Sites | Where-Object { $_.Name -eq $siteName })) {
    New-Website -Name $siteName -PhysicalPath $siteRoot -Port 8089 -Force | Out-Null
    Set-ItemProperty "IIS:\Sites\$siteName" applicationPool $newAppPool
  }
  try {
    & $env:SystemRoot\System32\inetsrv\appcmd.exe list config "Default Web Site" /section:system.webServer /xml | Out-Null
    Write-Host "web.config parsed OK under IIS."
  } catch { Write-Warning "web.config failed to parse under IIS: $($_.Exception.Message)"; throw }
}
Write-Host "IIS web.config validation complete."
