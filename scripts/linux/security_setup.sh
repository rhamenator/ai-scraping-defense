#!/bin/bash
set -euo pipefail

python -m pip install --upgrade pip
pip install -r requirements.txt

# Install tools used by security_scan.sh
apt-get update
apt-get install -y \
    nmap nikto zaproxy sqlmap lynis hydra masscan gobuster enum4linux \
    wpscan ffuf wfuzz testssl.sh whatweb gvm rkhunter chkrootkit clamav jq

# Additional tools from GitHub with checksum verification
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

# Trivy
TRIVY_VERSION=$(curl -s https://api.github.com/repos/aquasecurity/trivy/releases/latest \
  | jq -r '.tag_name' | sed 's/^v//')
TRIVY_TAR="trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz"
curl -fsSL -o "$TMP_DIR/$TRIVY_TAR" \
  "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/$TRIVY_TAR"
curl -fsSL -o "$TMP_DIR/trivy_checksums.txt" \
  "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_checksums.txt"
(cd "$TMP_DIR" && grep "$TRIVY_TAR" trivy_checksums.txt | sha256sum -c -)
tar -xz -C /usr/local/bin -f "$TMP_DIR/$TRIVY_TAR" trivy
rm "$TMP_DIR/$TRIVY_TAR" "$TMP_DIR/trivy_checksums.txt"

# Gitleaks
GITLEAKS_VERSION=$(curl -s https://api.github.com/repos/gitleaks/gitleaks/releases/latest \
  | jq -r '.tag_name' | sed 's/^v//')
GITLEAKS_TAR="gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"
curl -fsSL -o "$TMP_DIR/$GITLEAKS_TAR" \
  "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/$GITLEAKS_TAR"
curl -fsSL -o "$TMP_DIR/gitleaks_checksums.txt" \
  "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_checksums.txt"
(cd "$TMP_DIR" && grep "$GITLEAKS_TAR" gitleaks_checksums.txt | sha256sum -c -)
tar -xz -C /usr/local/bin -f "$TMP_DIR/$GITLEAKS_TAR" gitleaks
rm "$TMP_DIR/$GITLEAKS_TAR" "$TMP_DIR/gitleaks_checksums.txt"

# Grype
GRYPE_VERSION=$(curl -s https://api.github.com/repos/anchore/grype/releases/latest \
  | jq -r '.tag_name' | sed 's/^v//')
GRYPE_TAR="grype_${GRYPE_VERSION}_linux_amd64.tar.gz"
curl -fsSL -o "$TMP_DIR/$GRYPE_TAR" \
  "https://github.com/anchore/grype/releases/download/v${GRYPE_VERSION}/$GRYPE_TAR"
curl -fsSL -o "$TMP_DIR/grype_checksums.txt" \
  "https://github.com/anchore/grype/releases/download/v${GRYPE_VERSION}/grype_${GRYPE_VERSION}_checksums.txt"
(cd "$TMP_DIR" && grep "$GRYPE_TAR" grype_checksums.txt | sha256sum -c -)
tar -xz -C /usr/local/bin -f "$TMP_DIR/$GRYPE_TAR" grype
rm "$TMP_DIR/$GRYPE_TAR" "$TMP_DIR/grype_checksums.txt"

# Nuclei
echo "Installing Nuclei..."
go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest || true
cp ~/go/bin/nuclei /usr/local/bin/ 2>/dev/null || echo "Note: nuclei not in ~/go/bin, may need manual PATH setup"

# Feroxbuster
FEROX_VERSION=$(curl -s https://api.github.com/repos/epi052/feroxbuster/releases/latest \
  | jq -r '.tag_name' | sed 's/^v//')
FEROX_TAR="feroxbuster_${FEROX_VERSION}_x86_64-linux.tar.gz"
curl -fsSL -o "$TMP_DIR/$FEROX_TAR" \
  "https://github.com/epi052/feroxbuster/releases/download/v${FEROX_VERSION}/x86_64-linux-feroxbuster.tar.gz" || true
if [[ -f "$TMP_DIR/$FEROX_TAR" ]]; then
    tar -xz -C /usr/local/bin -f "$TMP_DIR/$FEROX_TAR" feroxbuster 2>/dev/null || true
fi

# Katana
echo "Installing Katana..."
go install github.com/projectdiscovery/katana/cmd/katana@latest || true
cp ~/go/bin/katana /usr/local/bin/ 2>/dev/null || true

# httpx
echo "Installing httpx..."
go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest || true
cp ~/go/bin/httpx /usr/local/bin/ 2>/dev/null || true

# Dalfox
echo "Installing Dalfox..."
go install github.com/hahwul/dalfox/v2@latest || true
cp ~/go/bin/dalfox /usr/local/bin/ 2>/dev/null || true

# Amass
echo "Installing Amass..."
go install -v github.com/owasp-amass/amass/v4/...@master || true
cp ~/go/bin/amass /usr/local/bin/ 2>/dev/null || true

# Syft SBOM tool
SYFT_VERSION=$(curl -s https://api.github.com/repos/anchore/syft/releases/latest \
  | jq -r '.tag_name' | sed 's/^v//')
curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin || true

# Python security tools
pip install bandit sslyze sublist3r pip-audit safety semgrep schemathesis

# Snyk CLI (requires account but useful)
npm install -g snyk 2>/dev/null || echo "Note: npm not available for snyk installation"

# Make new scripts executable
chmod +x /home/runner/work/ai-scraping-defense/ai-scraping-defense/scripts/linux/api_security_test.sh 2>/dev/null || true
chmod +x /home/runner/work/ai-scraping-defense/ai-scraping-defense/scripts/linux/llm_prompt_injection_test.sh 2>/dev/null || true
chmod +x /home/runner/work/ai-scraping-defense/ai-scraping-defense/scripts/linux/ai_driven_security_test.py 2>/dev/null || true

apt-get clean

# Apply security hardening settings from config
# TODO: Implement bash-based hardening configuration
echo "Applying security hardening settings..."
echo "(Currently a placeholder. Implement config loading and applying.)"
echo "Security tools installation complete!"
echo "Note: Some Go-based tools may require adding ~/go/bin to PATH"
