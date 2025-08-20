#!/bin/zsh
set -euo pipefail

python -m pip install --upgrade pip
pip install -r requirements.txt

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew not found. Install it from https://brew.sh" >&2
  exit 1
fi

# Install tools used by security_scan.sh
brew update
brew install nmap nikto zaproxy sqlmap lynis hydra masscan gobuster enum4linux \
    wpscan ffuf wfuzz testssl whatweb gvm rkhunter chkrootkit clamav jq

# Additional tools from GitHub with checksum verification
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

# Trivy
TRIVY_VERSION=$(curl -s https://api.github.com/repos/aquasecurity/trivy/releases/latest \
  | jq -r '.tag_name' | sed 's/^v//')
TRIVY_TAR="trivy_${TRIVY_VERSION}_macOS-64bit.tar.gz"
curl -fsSL -o "$TMP_DIR/$TRIVY_TAR" \
  "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/$TRIVY_TAR"
curl -fsSL -o "$TMP_DIR/trivy_checksums.txt" \
  "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_checksums.txt"
(cd "$TMP_DIR" && grep "$TRIVY_TAR" trivy_checksums.txt | shasum -a 256 -c -)
tar -xz -C "$INSTALL_DIR" -f "$TMP_DIR/$TRIVY_TAR" trivy
rm "$TMP_DIR/$TRIVY_TAR" "$TMP_DIR/trivy_checksums.txt"

# Gitleaks
GITLEAKS_VERSION=$(curl -s https://api.github.com/repos/gitleaks/gitleaks/releases/latest \
  | jq -r '.tag_name' | sed 's/^v//')
GITLEAKS_TAR="gitleaks_${GITLEAKS_VERSION}_macos_x64.tar.gz"
curl -fsSL -o "$TMP_DIR/$GITLEAKS_TAR" \
  "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/$GITLEAKS_TAR"
curl -fsSL -o "$TMP_DIR/gitleaks_checksums.txt" \
  "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_checksums.txt"
(cd "$TMP_DIR" && grep "$GITLEAKS_TAR" gitleaks_checksums.txt | shasum -a 256 -c -)
tar -xz -C /usr/local/bin -f "$TMP_DIR/$GITLEAKS_TAR" gitleaks
rm "$TMP_DIR/$GITLEAKS_TAR" "$TMP_DIR/gitleaks_checksums.txt"

# Grype
GRYPE_VERSION=$(curl -s https://api.github.com/repos/anchore/grype/releases/latest \
  | jq -r '.tag_name' | sed 's/^v//')
GRYPE_TAR="grype_${GRYPE_VERSION}_darwin_amd64.tar.gz"
curl -fsSL -o "$TMP_DIR/$GRYPE_TAR" \
  "https://github.com/anchore/grype/releases/download/v${GRYPE_VERSION}/$GRYPE_TAR"
curl -fsSL -o "$TMP_DIR/grype_checksums.txt" \
  "https://github.com/anchore/grype/releases/download/v${GRYPE_VERSION}/grype_${GRYPE_VERSION}_checksums.txt"
(cd "$TMP_DIR" && grep "$GRYPE_TAR" grype_checksums.txt | shasum -a 256 -c -)
tar -xz -C /usr/local/bin -f "$TMP_DIR/$GRYPE_TAR" grype
rm "$TMP_DIR/$GRYPE_TAR" "$TMP_DIR/grype_checksums.txt"

pip install bandit sslyze sublist3r pip-audit
brew cleanup
