#!/bin/bash
# security_scan.sh - Advanced security testing helper
#

# Usage: sudo ./security_scan.sh <target_host_or_ip> [web_url_for_nikto] [docker_image] [code_dir] [sqlmap_url]
# - target_host_or_ip: IP or hostname for network scans
# - web_url_for_nikto: full URL to scan with Nikto and ZAP (defaults to http://<target>)
# - docker_image: optional container image to scan with Trivy
# - code_dir: optional path to source code for Bandit static analysis
# - sqlmap_url: optional parameterized URL for automated SQLMap testing

set -e

TARGET="$1"
WEB_URL="${2:-http://$1}"
IMAGE="$3"
CODE_DIR="${4:-.}"

SQLMAP_URL="$5"
PORTS="22,80,443,5432,6379"

if [[ -z "$TARGET" ]]; then
    echo "Usage: sudo $0 <target_host_or_ip> [web_url_for_nikto] [docker_image] [code_dir] [sqlmap_url]"
    exit 1
fi

mkdir -p reports

echo "=== 1. Nmap Scan (version, OS, common vulns) ==="
if command -v nmap >/dev/null 2>&1; then
    nmap -A -p "$PORTS" --script=vuln -oN "reports/nmap_${TARGET}.txt" "$TARGET"
else
    echo "nmap not installed. Skipping nmap scan."
fi

echo "=== 2. Nikto Web Scan ==="
if command -v nikto >/dev/null 2>&1; then
    nikto -host "$WEB_URL" -output "reports/nikto_$(echo $WEB_URL | tr '/:' '_').txt"
else
    echo "nikto not installed. Skipping Nikto scan."
fi

echo "=== 3. OWASP ZAP Baseline Scan ==="
if command -v zap-baseline.py >/dev/null 2>&1; then
    zap-baseline.py -t "$WEB_URL" -w "reports/zap_$(echo $WEB_URL | tr '/:' '_').html" -r "zap_${TARGET}.md"
else
    echo "zap-baseline.py not installed. Skipping ZAP scan."
fi

echo "=== 4. SQLMap (optional automated scan) ==="
if [[ -n "$SQLMAP_URL" ]]; then
    if command -v sqlmap >/dev/null 2>&1; then
        sqlmap -u "$SQLMAP_URL" --batch -oN "reports/sqlmap_$(echo $TARGET | tr '/:' '_').txt"
    else
        echo "sqlmap not installed. Skipping SQL injection test."
    fi
else
    echo "  Provide a parameterized URL as sqlmap_url to run SQLMap automatically."
    echo "  Example: sqlmap -u 'http://$TARGET/vuln.php?id=1' --batch -oN reports/sqlmap_${TARGET}.txt"
fi

if [[ -n "$IMAGE" ]]; then
    echo "=== 5. Trivy Container Scan ==="
    if command -v trivy >/dev/null 2>&1; then
        trivy image -o "reports/trivy_$(echo $IMAGE | tr '/:' '_').txt" "$IMAGE"
    else
        echo "trivy not installed. Skipping image scan."
    fi
fi

if [[ -d "$CODE_DIR" ]]; then
    echo "=== 6. Bandit Static Code Analysis ==="
    if command -v bandit >/dev/null 2>&1; then
        bandit -r "$CODE_DIR" -f txt -o "reports/bandit_$(basename $CODE_DIR).txt"
    else
        echo "bandit not installed. Skipping static analysis."
    fi
fi

echo "=== 7. OpenVAS (Greenbone) ==="
echo "  Ensure OpenVAS is initialized and running. Example gvm-cli command:" 
echo "      gvm-cli socket -- gmp start_task <task-id>"

echo "=== 8. Lynis System Audit ==="
if command -v lynis >/dev/null 2>&1; then
    lynis audit system --quiet --logfile reports/lynis.log --report-file reports/lynis-report.txt
else
    echo "lynis not installed. Skipping system audit."
fi

echo "=== 9. Optional Hydra Password Test ==="
echo "  hydra -L users.txt -P passwords.txt ssh://$TARGET -o reports/hydra_${TARGET}.txt"

echo "=== 10. Masscan Quick Sweep ==="
if command -v masscan >/dev/null 2>&1; then
    echo "  Running a fast port sweep (rate 1000) on $TARGET"
    masscan -p"$PORTS" "$TARGET" --rate=1000 -oL "reports/masscan_${TARGET}.txt"
else
    echo "masscan not installed. Skipping quick sweep."
fi

echo "=== 11. Gobuster Directory Scan ==="
if command -v gobuster >/dev/null 2>&1; then
    gobuster dir -u "$WEB_URL" -w /usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt \
        -o "reports/gobuster_$(echo $WEB_URL | tr '/:' '_').txt"
else
    echo "gobuster not installed. Skipping directory scan."
fi

echo "=== 12. Enum4linux SMB Enumeration ==="
if command -v enum4linux >/dev/null 2>&1; then
    enum4linux -a "$TARGET" | tee "reports/enum4linux_${TARGET}.txt"
else
    echo "enum4linux not installed. Skipping SMB enumeration."
fi

echo "=== 13. WPScan (WordPress) ==="
if command -v wpscan >/dev/null 2>&1; then
    wpscan --url "$WEB_URL" --no-update -o "reports/wpscan_$(echo $WEB_URL | tr '/:' '_').txt"
else
    echo "wpscan not installed. Skipping WordPress scan."
fi

echo "=== 14. SSLyze TLS Scan ==="
if command -v sslyze >/dev/null 2>&1; then
    sslyze --regular "$TARGET" > "reports/sslyze_${TARGET}.txt"
else
    echo "sslyze not installed. Skipping TLS scan."
fi

echo "=== 15. ffuf Web Fuzzing ==="
if command -v ffuf >/dev/null 2>&1; then
    WORDLIST="/usr/share/seclists/Discovery/Web-Content/common.txt"
    if [[ -f "$WORDLIST" ]]; then
        ffuf -w "$WORDLIST" -u "${WEB_URL}/FUZZ" -of csv -o "reports/ffuf_$(echo $WEB_URL | tr '/:' '_').csv"
    else
        echo "Wordlist $WORDLIST not found. Skipping ffuf fuzzing."
    fi
else
    echo "ffuf not installed. Skipping web fuzzing."
fi

echo "=== 16. Wfuzz Parameter Fuzzing ==="
if command -v wfuzz >/dev/null 2>&1; then
    PARAM_LIST="/usr/share/seclists/Discovery/Web-Content/burp-parameter-names.txt"
    if [[ -f "$PARAM_LIST" ]]; then
        wfuzz -c -z file,"$PARAM_LIST" -d "FUZZ=test" "$WEB_URL" | tee "reports/wfuzz_$(echo $WEB_URL | tr '/:' '_').txt"
    else
        echo "Parameter wordlist $PARAM_LIST not found. Skipping wfuzz."
    fi
else
    echo "wfuzz not installed. Skipping parameter fuzzing."
fi

echo "=== 17. testssl TLS Scan ==="
if command -v testssl.sh >/dev/null 2>&1; then
    testssl.sh "$WEB_URL" > "reports/testssl_$(echo $WEB_URL | tr '/:' '_').txt"
else
    echo "testssl.sh not installed. Skipping TLS scan."
fi

echo "=== 18. WhatWeb Fingerprinting ==="
if command -v whatweb >/dev/null 2>&1; then
    whatweb "$WEB_URL" > "reports/whatweb_$(echo $WEB_URL | tr '/:' '_').txt"
else
    echo "whatweb not installed. Skipping fingerprinting."
fi

echo "=== 19. Gitleaks Secret Scan ==="
if command -v gitleaks >/dev/null 2>&1; then
    gitleaks detect -s "$CODE_DIR" -v --report-path "reports/gitleaks_$(basename $CODE_DIR).txt" || true
else
    echo "gitleaks not installed. Skipping secrets scan."
fi

echo "=== 20. Grype Container Scan ==="
if [[ -n "$IMAGE" ]] && command -v grype >/dev/null 2>&1; then
    grype "$IMAGE" -o table > "reports/grype_$(echo $IMAGE | tr '/:' '_').txt"
else
    echo "grype not installed or no image specified. Skipping grype scan."
fi

echo "=== 21. ClamAV Malware Scan ==="
if command -v clamscan >/dev/null 2>&1; then
    clamscan -r "$CODE_DIR" > "reports/clamscan_$(basename $CODE_DIR).txt"
else
    echo "clamscan not installed. Skipping malware scan."
fi

echo "=== 22. Rkhunter Rootkit Check ==="
if command -v rkhunter >/dev/null 2>&1; then
    rkhunter --check --sk --rwo > "reports/rkhunter_${TARGET}.txt" || true
else
    echo "rkhunter not installed. Skipping rootkit check."
fi

echo "=== 23. Chkrootkit Rootkit Check ==="
if command -v chkrootkit >/dev/null 2>&1; then
    chkrootkit > "reports/chkrootkit_${TARGET}.txt"
else
    echo "chkrootkit not installed. Skipping rootkit check."
fi

echo "=== 24. Sublist3r Subdomain Enumeration ==="
if command -v sublist3r >/dev/null 2>&1; then
    sublist3r -d "$TARGET" -o "reports/sublist3r_${TARGET}.txt"
else
    echo "sublist3r not installed. Skipping subdomain enumeration."
fi

echo "=== 25. pip-audit Dependency Scan ==="
if command -v pip-audit >/dev/null 2>&1; then
    pip-audit -r requirements.txt -f plain > "reports/pip_audit.txt" || true
else
    echo "pip-audit not installed. Skipping Python dependency audit."
fi

echo "Reports saved in the 'reports' directory. Review them for potential issues." 
