[CmdletBinding()] param()
$haveChoco = Get-Command choco -ErrorAction SilentlyContinue
if ($haveChoco) {
  try {
    choco install urlrewrite -y --no-progress
    choco install iis-arr -y --no-progress
    Write-Host "Installed URL Rewrite + ARR via Chocolatey."; exit 0
  } catch { Write-Warning "Chocolatey install failed, falling back to direct download." }
}
$downloads = @(
  @{ Name="URL Rewrite"; Url="https://download.microsoft.com/download/D/D/9/DD9A5C5C-69F9-483E-9B5F-F8F1D13C8F9D/rewrite_amd64.msi"; File="$env:TEMP\rewrite_amd64.msi" },
  @{ Name="ARR";         Url="https://download.microsoft.com/download/1/1/2/1123E95C-4E08-4C6A-8D9B-D7D1D7E98A2E/requestRouter_amd64.msi"; File="$env:TEMP\requestRouter_amd64.msi" }
)
foreach ($d in $downloads) {
  try { Invoke-WebRequest -Uri $d.Url -OutFile $d.File -UseBasicParsing; Start-Process msiexec.exe -Wait -ArgumentList "/i `"$($d.File)`" /qn /norestart"; Write-Host "Installed $($d.Name)." }
  catch { Write-Warning "Failed to install $($d.Name): $($_.Exception.Message)" }
}
