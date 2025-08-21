param([string]$SiteName = "AI-Scraping-Defense-Temp",[int]$Port = 8081)
Import-Module WebAdministration -ErrorAction SilentlyContinue
$siteRoot = Join-Path $env:TEMP $SiteName; New-Item -ItemType Directory -Path $siteRoot -Force | Out-Null
Set-Content -Path (Join-Path $siteRoot "index.html") -Value "<h1>$SiteName</h1>" -Encoding UTF8
$cfg = Get-ChildItem -Recurse -Filter web.config -ErrorAction SilentlyContinue | Select-Object -First 1
if ($cfg) { Copy-Item $cfg.FullName (Join-Path $siteRoot "web.config") -Force }
if (Get-ChildItem IIS:\Sites | Where-Object { $_.Name -eq $SiteName }) { Remove-Website -Name $SiteName -Confirm:$false }
New-Website -Name $SiteName -Port $Port -PhysicalPath $siteRoot -Force | Out-Null
Write-Host "Started IIS site $SiteName at http://localhost:$Port/"
