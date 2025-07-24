#!/bin/bash
# security_scan.sh - Advanced security testing helper
#
# Usage: sudo ./security_scan.sh <target_host_or_ip> [web_url_for_nikto] [docker_image] [code_dir]
# - target_host_or_ip: IP or hostname for network scans
# - web_url_for_nikto: full URL to scan with Nikto and ZAP (defaults to http://<target>)
# - docker_image: optional container image to scan with Trivy
# - code_dir: optional path to source code for Bandit static analysis

set -e

TARGET="$1"
WEB_URL="${2:-http://$1}"
IMAGE="$3"
CODE_DIR="${4:-.}"

if [[ -z "$TARGET" ]]; then
    echo "Usage: sudo $0 <target_host_or_ip> [web_url_for_nikto] [docker_image] [code_dir]"
    exit 1
fi

mkdir -p reports

echo "=== 1. Nmap Scan (version, OS, common vulns) ==="
nmap -A --script=vuln -oN "reports/nmap_${TARGET}.txt" "$TARGET"

echo "=== 2. Nikto Web Scan ==="
nikto -host "$WEB_URL" -output "reports/nikto_$(echo $WEB_URL | tr '/:' '_').txt"

echo "=== 3. OWASP ZAP Baseline Scan ==="
if command -v zap-baseline.py >/dev/null 2>&1; then
    zap-baseline.py -t "$WEB_URL" -w "reports/zap_$(echo $WEB_URL | tr '/:' '_').html" -r "zap_${TARGET}.md"
else
    echo "zap-baseline.py not installed. Skipping ZAP scan."
fi

echo "=== 4. SQLMap (example usage) ==="
echo "  Customize the sqlmap command with the specific parameterized URL you wish to test."
echo "  Example: sqlmap -u 'http://$TARGET/vuln.php?id=1' --batch -oN reports/sqlmap_${TARGET}.txt"

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
lynis audit system --quiet --logfile reports/lynis.log --report-file reports/lynis-report.txt

echo "=== 9. Optional Hydra Password Test ==="
echo "  hydra -L users.txt -P passwords.txt ssh://$TARGET -o reports/hydra_${TARGET}.txt"

echo "Reports saved in the 'reports' directory. Review them for potential issues."
