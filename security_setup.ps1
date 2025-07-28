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

pip install bandit sslyze sublist3r pip-audit
