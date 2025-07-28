#!/bin/bash
set -e

python -m pip install --upgrade pip
pip install -r requirements.txt

# Install tools used by security_scan.sh
apt-get update
apt-get install -y \
    nmap nikto zaproxy sqlmap lynis hydra masscan gobuster enum4linux \
    wpscan ffuf wfuzz testssl.sh whatweb gvm rkhunter chkrootkit clamav

# Additional tools from GitHub
curl -L https://github.com/aquasecurity/trivy/releases/latest/download/trivy_0.50.1_Linux-64bit.tar.gz \
  | tar -xz -C /usr/local/bin --strip-components=1 trivy
curl -L https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks-linux-amd64 \
  -o /usr/local/bin/gitleaks && chmod +x /usr/local/bin/gitleaks
curl -L https://github.com/anchore/grype/releases/latest/download/grype_linux_amd64.tar.gz \
  | tar -xz -C /usr/local/bin grype

pip install bandit sslyze sublist3r pip-audit
apt-get clean
