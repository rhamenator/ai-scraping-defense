<#
.SYNOPSIS
Installs Python requirements and common security tools needed for security_scan.ps1.
#> 

python -m pip install --upgrade pip
pip install -r requirements.txt

$tools = @(
    'nmap','nikto','zaproxy','sqlmap','lynis','hydra','masscan','gobuster','enum4linux',
    'wpscan','ffuf','wfuzz','testssl.sh','whatweb','gvm','rkhunter','chkrootkit','clamav'
)

if (Get-Command choco -ErrorAction SilentlyContinue) {
    choco install -y $tools
} elseif (Get-Command winget -ErrorAction SilentlyContinue) {
    foreach ($t in $tools) {
        winget install --accept-package-agreements --accept-source-agreements -e --id $t
    }
} else {
    Write-Warning "Install the following tools manually: $($tools -join ', ')"
}

Invoke-WebRequest -Uri 'https://github.com/aquasecurity/trivy/releases/latest/download/trivy_0.50.1_Windows-64bit.zip' -OutFile trivy.zip
Expand-Archive trivy.zip -DestinationPath $Env:ProgramFiles
Remove-Item trivy.zip

Invoke-WebRequest -Uri 'https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks_amd64.exe' -OutFile $Env:ProgramFiles\gitleaks.exe

Invoke-WebRequest -Uri 'https://github.com/anchore/grype/releases/latest/download/grype_windows_amd64.zip' -OutFile grype.zip
Expand-Archive grype.zip -DestinationPath $Env:ProgramFiles
Remove-Item grype.zip

# Install Go-based security tools (requires Go to be installed)
if (Get-Command go -ErrorAction SilentlyContinue) {
    Write-Host "Installing Go-based security tools..."
    go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
    go install github.com/projectdiscovery/katana/cmd/katana@latest
    go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest
    go install github.com/hahwul/dalfox/v2@latest
    go install -v github.com/owasp-amass/amass/v4/...@master
} else {
    Write-Warning "Go not installed. Skipping Go-based tools (nuclei, katana, httpx, dalfox, amass)."
    Write-Warning "Install Go from https://golang.org/dl/ to enable these tools."
}

# Install Feroxbuster
if (Get-Command winget -ErrorAction SilentlyContinue) {
    winget install --accept-package-agreements --accept-source-agreements -e --id epi052.feroxbuster
} else {
    Write-Warning "winget not available. Install feroxbuster manually from GitHub."
}

# Install Syft SBOM tool
Invoke-WebRequest -Uri 'https://github.com/anchore/syft/releases/latest/download/syft_windows_amd64.zip' -OutFile syft.zip
Expand-Archive syft.zip -DestinationPath $Env:ProgramFiles
Remove-Item syft.zip

# Python security tools
pip install bandit sslyze sublist3r pip-audit safety semgrep schemathesis

# Snyk CLI (requires npm)
if (Get-Command npm -ErrorAction SilentlyContinue) {
    npm install -g snyk
} else {
    Write-Warning "npm not available. Install Node.js to enable Snyk."
}

Write-Host "Security tools installation complete!" -ForegroundColor Green
Write-Host "Note: Go-based tools are installed to $(go env GOPATH)\bin" -ForegroundColor Yellow
Write-Host "Add $(go env GOPATH)\bin to your PATH if not already present." -ForegroundColor Yellow

# Apply security hardening settings from config
# TODO: Implement PowerShell-based hardening configuration
Write-Host "Applying security hardening settings..."
Write-Host "(Currently a placeholder. Implement config loading and applying.)"
