#!/bin/bash
set -e
python -m pip install --upgrade pip
pip install -r requirements.txt
# Install tools used by security_scan.sh
apt-get update
apt-get install -y nmap nikto zaproxy sqlmap lynis
curl -L https://github.com/aquasecurity/trivy/releases/latest/download/trivy_0.50.1_Linux-64bit.tar.gz | tar -xz -C /usr/local/bin --strip-components=1 trivy
apt-get clean
