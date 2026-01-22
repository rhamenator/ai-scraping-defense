#!/bin/zsh
# security_scan.zsh - Advanced security testing helper
#

# Usage: sudo ./security_scan.zsh <target_host_or_ip> [web_url_for_nikto] [docker_image] [code_dir] [sqlmap_url] [api_base_url] [openapi_spec_url] [llm_endpoint] [llm_auth_token]
# - target_host_or_ip: IP or hostname for network scans
# - web_url_for_nikto: full URL to scan with Nikto and ZAP (defaults to http://<target>)
# - docker_image: optional container image to scan with Trivy
# - code_dir: optional path to source code for Bandit static analysis
# - sqlmap_url: optional parameterized URL for automated SQLMap testing
# - api_base_url: optional base URL for API security testing
# - openapi_spec_url: optional OpenAPI/Swagger spec URL for API security testing
# - llm_endpoint: optional AI/LLM endpoint for prompt injection testing
# - llm_auth_token: optional auth token for LLM prompt injection testing

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$SCRIPT_DIR/../security/scan_helpers.sh" ]]; then
    # shellcheck disable=SC1091
    . "$SCRIPT_DIR/../security/scan_helpers.sh"
else
    safe_name() { echo "$1" | tr '/:' '_'; }
    select_wordlist() {
        local override="$1"
        shift
        if [[ -n "$override" && -f "$override" ]]; then
            echo "$override"
            return 0
        fi
        for candidate in "$@"; do
            if [[ -f "$candidate" ]]; then
                echo "$candidate"
                return 0
            fi
        done
        return 1
    }
fi

TARGET="$1"
WEB_URL="${2:-http://$1}"
IMAGE="$3"
CODE_DIR="${4:-.}"

SQLMAP_URL="$5"
API_BASE_URL="${6:-}"
OPENAPI_SPEC_URL="${7:-}"
LLM_ENDPOINT="${8:-}"
LLM_AUTH_TOKEN="${9:-}"
PORTS="22,80,443,5432,6379"
SAFE_TARGET="$(safe_name "$TARGET")"
SAFE_WEB="$(safe_name "$WEB_URL")"
SAFE_IMAGE=""
if [[ -n "$IMAGE" ]]; then
    SAFE_IMAGE="$(safe_name "$IMAGE")"
fi

if [[ -z "$TARGET" ]]; then
    echo "Usage: sudo $0 <target_host_or_ip> [web_url_for_nikto] [docker_image] [code_dir] [sqlmap_url] [api_base_url] [openapi_spec_url] [llm_endpoint] [llm_auth_token]"
    exit 1
fi

mkdir -p reports

echo "=== 1. Nmap Scan (version, OS, common vulns) ==="
if command -v nmap >/dev/null 2>&1; then
    nmap -A -p "$PORTS" --script=vuln -oN "reports/nmap_${SAFE_TARGET}.txt" "$TARGET"
else
    echo "nmap not installed. Skipping nmap scan."
fi

echo "=== 2. Nikto Web Scan ==="
if command -v nikto >/dev/null 2>&1; then
    nikto -host "$WEB_URL" -output "reports/nikto_${SAFE_WEB}.txt"
else
    echo "nikto not installed. Skipping Nikto scan."
fi

echo "=== 3. OWASP ZAP Baseline Scan ==="
if command -v zap-baseline.py >/dev/null 2>&1; then
    zap-baseline.py -t "$WEB_URL" -w "reports/zap_${SAFE_WEB}.html" -r "zap_${SAFE_TARGET}.md"
else
    echo "zap-baseline.py not installed. Skipping ZAP scan."
fi

echo "=== 4. SQLMap (optional automated scan) ==="
if [[ -n "$SQLMAP_URL" ]]; then
    if command -v sqlmap >/dev/null 2>&1; then
        sqlmap -u "$SQLMAP_URL" --batch -oN "reports/sqlmap_${SAFE_TARGET}.txt"
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
        trivy image -o "reports/trivy_${SAFE_IMAGE}.txt" "$IMAGE"
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
echo "  hydra -L users.txt -P passwords.txt ssh://$TARGET -o reports/hydra_${SAFE_TARGET}.txt"

echo "=== 10. Masscan Quick Sweep ==="
if command -v masscan >/dev/null 2>&1; then
    echo "  Running a fast port sweep (rate 1000) on $TARGET"
    masscan -p"$PORTS" "$TARGET" --rate=1000 -oL "reports/masscan_${SAFE_TARGET}.txt"
else
    echo "masscan not installed. Skipping quick sweep."
fi

echo "=== 11. Gobuster Directory Scan ==="
if command -v gobuster >/dev/null 2>&1; then
    WORDLIST="$(select_wordlist \
        "${GOBUSTER_WORDLIST:-}" \
        "/usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt" \
        "/usr/local/share/wordlists/dirbuster/directory-list-2.3-medium.txt" \
        "/opt/homebrew/share/wordlists/dirbuster/directory-list-2.3-medium.txt" \
    )" || WORDLIST=""
    if [[ -n "$WORDLIST" ]]; then
        gobuster dir -u "$WEB_URL" -w "$WORDLIST" \
            -o "reports/gobuster_${SAFE_WEB}.txt"
    else
        echo "No suitable gobuster wordlist found. Set GOBUSTER_WORDLIST to override."
    fi
else
    echo "gobuster not installed. Skipping directory scan."
fi

echo "=== 12. Enum4linux SMB Enumeration ==="
if command -v enum4linux >/dev/null 2>&1; then
    enum4linux -a "$TARGET" | tee "reports/enum4linux_${SAFE_TARGET}.txt"
else
    echo "enum4linux not installed. Skipping SMB enumeration."
fi

echo "=== 13. WPScan (WordPress) ==="
if command -v wpscan >/dev/null 2>&1; then
    wpscan --url "$WEB_URL" --no-update -o "reports/wpscan_${SAFE_WEB}.txt"
else
    echo "wpscan not installed. Skipping WordPress scan."
fi

echo "=== 14. SSLyze TLS Scan ==="
if command -v sslyze >/dev/null 2>&1; then
    sslyze --regular "$TARGET" > "reports/sslyze_${SAFE_TARGET}.txt"
else
    echo "sslyze not installed. Skipping TLS scan."
fi

echo "=== 15. ffuf Web Fuzzing ==="
if command -v ffuf >/dev/null 2>&1; then
    WORDLIST="$(select_wordlist \
        "${FFUF_WORDLIST:-}" \
        "/usr/share/seclists/Discovery/Web-Content/common.txt" \
        "/usr/local/share/seclists/Discovery/Web-Content/common.txt" \
        "/opt/homebrew/share/seclists/Discovery/Web-Content/common.txt" \
        "$HOME/seclists/Discovery/Web-Content/common.txt" \
    )" || WORDLIST=""
    if [[ -n "$WORDLIST" ]]; then
        ffuf -w "$WORDLIST" -u "${WEB_URL}/FUZZ" -of csv -o "reports/ffuf_${SAFE_WEB}.csv"
    else
        echo "No suitable ffuf wordlist found. Set FFUF_WORDLIST to override."
    fi
else
    echo "ffuf not installed. Skipping web fuzzing."
fi

echo "=== 16. Wfuzz Parameter Fuzzing ==="
if command -v wfuzz >/dev/null 2>&1; then
    PARAM_LIST="$(select_wordlist \
        "${WFUZZ_PARAM_LIST:-}" \
        "/usr/share/seclists/Discovery/Web-Content/burp-parameter-names.txt" \
        "/usr/local/share/seclists/Discovery/Web-Content/burp-parameter-names.txt" \
        "/opt/homebrew/share/seclists/Discovery/Web-Content/burp-parameter-names.txt" \
    )" || PARAM_LIST=""
    if [[ -n "$PARAM_LIST" ]]; then
        wfuzz -c -z file,"$PARAM_LIST" -d "FUZZ=test" "$WEB_URL" | tee "reports/wfuzz_${SAFE_WEB}.txt"
    else
        echo "No suitable wfuzz parameter list found. Set WFUZZ_PARAM_LIST to override."
    fi
else
    echo "wfuzz not installed. Skipping parameter fuzzing."
fi

echo "=== 17. testssl TLS Scan ==="
if command -v testssl.sh >/dev/null 2>&1; then
    testssl.sh "$WEB_URL" > "reports/testssl_${SAFE_WEB}.txt"
else
    echo "testssl.sh not installed. Skipping TLS scan."
fi

echo "=== 18. WhatWeb Fingerprinting ==="
if command -v whatweb >/dev/null 2>&1; then
    whatweb "$WEB_URL" > "reports/whatweb_${SAFE_WEB}.txt"
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
    grype "$IMAGE" -o table > "reports/grype_${SAFE_IMAGE}.txt"
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
    rkhunter --check --sk --rwo > "reports/rkhunter_${SAFE_TARGET}.txt" || true
else
    echo "rkhunter not installed. Skipping rootkit check."
fi

echo "=== 23. Chkrootkit Rootkit Check ==="
if command -v chkrootkit >/dev/null 2>&1; then
    chkrootkit > "reports/chkrootkit_${SAFE_TARGET}.txt"
else
    echo "chkrootkit not installed. Skipping rootkit check."
fi

echo "=== 24. Sublist3r Subdomain Enumeration ==="
if command -v sublist3r >/dev/null 2>&1; then
    sublist3r -d "$TARGET" -o "reports/sublist3r_${SAFE_TARGET}.txt"
else
    echo "sublist3r not installed. Skipping subdomain enumeration."
fi

echo "=== 25. pip-audit Dependency Scan ==="
if command -v pip-audit >/dev/null 2>&1; then
    pip-audit -r requirements.txt -f plain > "reports/pip_audit.txt" || true
else
    echo "pip-audit not installed. Skipping Python dependency audit."
fi

echo "=== 26. Nuclei Vulnerability Scanner ==="
if command -v nuclei >/dev/null 2>&1; then
    nuclei -u "$WEB_URL" -o "reports/nuclei_${SAFE_WEB}.txt" -silent
else
    echo "nuclei not installed. Skipping Nuclei scan."
fi

echo "=== 27. Feroxbuster Advanced Web Fuzzer ==="
if command -v feroxbuster >/dev/null 2>&1; then
    WORDLIST="$(select_wordlist \
        "${FEROX_WORDLIST:-}" \
        "/usr/share/seclists/Discovery/Web-Content/common.txt" \
        "/usr/local/share/seclists/Discovery/Web-Content/common.txt" \
        "/opt/homebrew/share/seclists/Discovery/Web-Content/common.txt" \
        "$HOME/seclists/Discovery/Web-Content/common.txt" \
    )" || WORDLIST=""
    if [[ -n "$WORDLIST" ]]; then
        feroxbuster -u "$WEB_URL" -w "$WORDLIST" \
            -o "reports/feroxbuster_${SAFE_WEB}.txt" --quiet || true
    else
        echo "No suitable feroxbuster wordlist found. Set FEROX_WORDLIST to override."
    fi
else
    echo "feroxbuster not installed. Skipping advanced fuzzing."
fi

echo "=== 28. Katana Web Crawler ==="
if command -v katana >/dev/null 2>&1; then
    katana -u "$WEB_URL" -o "reports/katana_${SAFE_WEB}.txt" -silent || true
else
    echo "katana not installed. Skipping web crawling."
fi

echo "=== 29. HTTPX HTTP Toolkit ==="
if command -v httpx >/dev/null 2>&1; then
    echo "$WEB_URL" | httpx -silent -tech-detect -status-code -title \
        -o "reports/httpx_${SAFE_WEB}.txt" || true
else
    echo "httpx not installed. Skipping HTTP analysis."
fi

echo "=== 30. Dalfox XSS Scanner ==="
if command -v dalfox >/dev/null 2>&1; then
    dalfox url "$WEB_URL" -o "reports/dalfox_${SAFE_WEB}.txt" --silence || true
else
    echo "dalfox not installed. Skipping XSS scanning."
fi

echo "=== 31. Amass Subdomain/Asset Discovery ==="
if command -v amass >/dev/null 2>&1; then
    amass enum -passive -d "$TARGET" -o "reports/amass_${SAFE_TARGET}.txt" || true
else
    echo "amass not installed. Skipping subdomain discovery."
fi

echo "=== 32. Semgrep Code Security Analysis ==="
if command -v semgrep >/dev/null 2>&1 && [[ -d "$CODE_DIR" ]]; then
    semgrep --config=auto "$CODE_DIR" --json -o "reports/semgrep_$(basename $CODE_DIR).json" || true
else
    echo "semgrep not installed or no code directory. Skipping semgrep scan."
fi

echo "=== 33. Snyk Security Testing ==="
if command -v snyk >/dev/null 2>&1 && [[ -d "$CODE_DIR" ]]; then
    cd "$CODE_DIR" && snyk test --json-file-output="$(pwd)/reports/snyk_$(basename $CODE_DIR).json" || true
    cd - >/dev/null
else
    echo "snyk not installed or no code directory. Skipping Snyk scan."
fi

echo "=== 34. Safety Python Package Scanner ==="
if command -v safety >/dev/null 2>&1; then
    safety check --json -o "reports/safety_check.json" || true
else
    echo "safety not installed. Skipping Safety scan."
fi

echo "=== 35. Syft SBOM Generator ==="
if command -v syft >/dev/null 2>&1 && [[ -n "$IMAGE" ]]; then
    syft "$IMAGE" -o json > "reports/syft_${SAFE_IMAGE}.json" || true
else
    echo "syft not installed or no image specified. Skipping SBOM generation."
fi

echo "=== 36. Static Security Configuration Checks ==="
if command -v python3 >/dev/null 2>&1 && [[ -f "scripts/security/run_static_security_checks.py" ]]; then
    python3 scripts/security/run_static_security_checks.py \
        > "reports/static_security_checks.txt" 2>&1 || true
else
    echo "python3 or static security checks script not found. Skipping."
fi

echo "=== 37. API Security Test Suite ==="
if [[ -n "$API_BASE_URL" ]] && [[ -x "scripts/macos/api_security_test.zsh" ]]; then
    ./scripts/macos/api_security_test.zsh "$API_BASE_URL" "$OPENAPI_SPEC_URL" || true
else
    echo "API base URL or api_security_test.zsh missing. Skipping API tests."
fi

echo "=== 38. LLM Prompt Injection Tests ==="
if [[ -n "$LLM_ENDPOINT" ]] && [[ -x "scripts/macos/llm_prompt_injection_test.zsh" ]]; then
    ./scripts/macos/llm_prompt_injection_test.zsh "$LLM_ENDPOINT" "$LLM_AUTH_TOKEN" || true
else
    echo "LLM endpoint or llm_prompt_injection_test.zsh missing. Skipping LLM tests."
fi

echo "=== 39. AI-Driven Scan Correlation ==="
if command -v python3 >/dev/null 2>&1 && [[ -f "scripts/macos/ai_driven_security_test.py" ]]; then
    python3 scripts/macos/ai_driven_security_test.py \
        --reports-dir reports \
        --provider "${AI_SECURITY_PROVIDER:-local}" \
        --output reports/ai_analysis.txt || true
else
    echo "python3 or ai_driven_security_test.py missing. Skipping AI analysis."
fi

echo "Reports saved in the 'reports' directory. Review them for potential issues."
