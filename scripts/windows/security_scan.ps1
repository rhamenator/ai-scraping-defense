<#
.SYNOPSIS
    Windows PowerShell version of security_scan.sh.
.DESCRIPTION
    Runs a suite of common security scanners against a target host or web URL.
.PARAMETER Target
    Hostname or IP address to scan.
.PARAMETER WebUrl
    Full URL to test with web scanners. Defaults to http://<Target>.
.PARAMETER DockerImage
    Optional container image to scan with Trivy and Grype.
.PARAMETER CodeDir
    Path to source code for Bandit, Gitleaks, and ClamAV scans. Defaults to current directory.
.PARAMETER SqlmapUrl
    Parameterized URL for automated SQLMap testing.
.PARAMETER ApiBaseUrl
    Optional base URL for API security testing.
.PARAMETER OpenApiSpecUrl
    Optional OpenAPI/Swagger spec URL for API security testing.
.PARAMETER LlmEndpoint
    Optional AI/LLM endpoint for prompt injection testing.
.PARAMETER LlmAuthToken
    Optional auth token for LLM prompt injection testing.
#>
param(
    [Parameter(Mandatory=$true)][string]$Target,
    [string]$WebUrl,
    [string]$DockerImage,
    [string]$CodeDir = '.',
    [string]$SqlmapUrl,
    [string]$ApiBaseUrl,
    [string]$OpenApiSpecUrl,
    [string]$LlmEndpoint,
    [string]$LlmAuthToken
)

if (-not $WebUrl) { $WebUrl = "http://$Target" }
$Ports = '22,80,443,5432,6379'
$SafeTarget = $Target -replace '[:/]', '_'
$SafeWeb = $WebUrl -replace '[:/]', '_'
if ($DockerImage) { $SafeImage = $DockerImage -replace '[:/]', '_' }

$ErrorActionPreference = 'Stop'
if (-not (Test-Path 'reports')) { New-Item -ItemType Directory 'reports' | Out-Null }

Write-Host '=== 0. HTTP Stack Probe (quick regression checks) ==='
if ((Get-Command python -ErrorAction SilentlyContinue) -and (Test-Path 'scripts/security/stack_probe.py')) {
    python scripts/security/stack_probe.py --base-url $WebUrl --json *> "reports/stack_probe_${SafeWeb}.json" || $true
} else { Write-Warning 'python or scripts/security/stack_probe.py not found. Skipping stack probe.' }

Write-Host '=== 1. Nmap Scan (version, OS, common vulns) ==='
if (Get-Command nmap -ErrorAction SilentlyContinue) {
    nmap -A -p $Ports --script=vuln -oN "reports/nmap_${SafeTarget}.txt" $Target
} else { Write-Warning 'nmap not installed. Skipping nmap scan.' }

Write-Host '=== 2. Nikto Web Scan ==='
if (Get-Command nikto -ErrorAction SilentlyContinue) {
    nikto -host $WebUrl -output "reports/nikto_${SafeWeb}.txt"
} else { Write-Warning 'nikto not installed. Skipping Nikto scan.' }

Write-Host '=== 3. OWASP ZAP Baseline Scan ==='
if (Get-Command zap-baseline.py -ErrorAction SilentlyContinue) {
    zap-baseline.py -t $WebUrl -w "reports/zap_${SafeWeb}.html" -r "zap_${SafeTarget}.md"
} else { Write-Warning 'zap-baseline.py not installed. Skipping ZAP scan.' }

Write-Host '=== 4. SQLMap (optional automated scan) ==='
if ($SqlmapUrl) {
    if (Get-Command sqlmap -ErrorAction SilentlyContinue) {
        sqlmap -u $SqlmapUrl --batch -oN "reports/sqlmap_${SafeTarget}.txt"
    } else { Write-Warning 'sqlmap not installed. Skipping SQL injection test.' }
} else {
    Write-Host '  Provide -SqlmapUrl to run SQLMap automatically.'
}

if ($DockerImage) {
    Write-Host '=== 5. Trivy Container Scan ==='
    if (Get-Command trivy -ErrorAction SilentlyContinue) {
        trivy image -o "reports/trivy_${SafeImage}.txt" $DockerImage
    } else { Write-Warning 'trivy not installed. Skipping image scan.' }
}

if (Test-Path $CodeDir) {
    Write-Host '=== 6. Bandit Static Code Analysis ==='
    if (Get-Command bandit -ErrorAction SilentlyContinue) {
        bandit -r $CodeDir -f txt -o "reports/bandit_$(Split-Path $CodeDir -Leaf).txt"
    } else { Write-Warning 'bandit not installed. Skipping static analysis.' }
}

Write-Host '=== 7. OpenVAS (Greenbone) ==='
Write-Host '  Ensure OpenVAS is running. Example gvm-cli command:'
Write-Host '      gvm-cli socket -- gmp start_task <task-id>'

Write-Host '=== 8. Lynis System Audit ==='
if (Get-Command lynis -ErrorAction SilentlyContinue) {
    lynis audit system --quiet --logfile reports/lynis.log --report-file reports/lynis-report.txt
} else { Write-Warning 'lynis not installed. Skipping system audit.' }

Write-Host '=== 9. Optional Hydra Password Test ==='
Write-Host "  hydra -L users.txt -P passwords.txt ssh://$Target -o reports/hydra_${SafeTarget}.txt"

Write-Host '=== 10. Masscan Quick Sweep ==='
if (Get-Command masscan -ErrorAction SilentlyContinue) {
    Write-Host "  Running a fast port sweep (rate 1000) on $Target"
    masscan -p$Ports $Target --rate=1000 -oL "reports/masscan_${SafeTarget}.txt"
} else { Write-Warning 'masscan not installed. Skipping quick sweep.' }

Write-Host '=== 11. Gobuster Directory Scan ==='
if (Get-Command gobuster -ErrorAction SilentlyContinue) {
    $wordlist = '/usr/share/wordlists/dirbuster/directory-list-2.3-medium.txt'
    gobuster dir -u $WebUrl -w $wordlist -o "reports/gobuster_${SafeWeb}.txt"
} else { Write-Warning 'gobuster not installed. Skipping directory scan.' }

Write-Host '=== 12. Enum4linux SMB Enumeration ==='
if (Get-Command enum4linux -ErrorAction SilentlyContinue) {
    enum4linux -a $Target | Tee-Object "reports/enum4linux_${SafeTarget}.txt"
} else { Write-Warning 'enum4linux not installed. Skipping SMB enumeration.' }

Write-Host '=== 13. WPScan (WordPress) ==='
if (Get-Command wpscan -ErrorAction SilentlyContinue) {
    wpscan --url $WebUrl --no-update -o "reports/wpscan_${SafeWeb}.txt"
} else { Write-Warning 'wpscan not installed. Skipping WordPress scan.' }

Write-Host '=== 14. SSLyze TLS Scan ==='
if (Get-Command sslyze -ErrorAction SilentlyContinue) {
    sslyze --regular $Target > "reports/sslyze_${SafeTarget}.txt"
} else { Write-Warning 'sslyze not installed. Skipping TLS scan.' }

Write-Host '=== 15. ffuf Web Fuzzing ==='
if (Get-Command ffuf -ErrorAction SilentlyContinue) {
    $wl = '/usr/share/seclists/Discovery/Web-Content/common.txt'
    if (Test-Path $wl) {
        ffuf -w $wl -u "${WebUrl}/FUZZ" -of csv -o "reports/ffuf_${SafeWeb}.csv"
    } else { Write-Warning "Wordlist $wl not found. Skipping ffuf fuzzing." }
} else { Write-Warning 'ffuf not installed. Skipping web fuzzing.' }

Write-Host '=== 16. Wfuzz Parameter Fuzzing ==='
if (Get-Command wfuzz -ErrorAction SilentlyContinue) {
    $params = '/usr/share/seclists/Discovery/Web-Content/burp-parameter-names.txt'
    if (Test-Path $params) {
        wfuzz -c -z file,$params -d 'FUZZ=test' $WebUrl | Tee-Object "reports/wfuzz_${SafeWeb}.txt"
    } else { Write-Warning "Parameter wordlist $params not found. Skipping wfuzz." }
} else { Write-Warning 'wfuzz not installed. Skipping parameter fuzzing.' }

Write-Host '=== 17. testssl TLS Scan ==='
if (Get-Command testssl.sh -ErrorAction SilentlyContinue) {
    testssl.sh $WebUrl > "reports/testssl_${SafeWeb}.txt"
} else { Write-Warning 'testssl.sh not installed. Skipping TLS scan.' }

Write-Host '=== 18. WhatWeb Fingerprinting ==='
if (Get-Command whatweb -ErrorAction SilentlyContinue) {
    whatweb $WebUrl > "reports/whatweb_${SafeWeb}.txt"
} else { Write-Warning 'whatweb not installed. Skipping fingerprinting.' }

Write-Host '=== 19. Gitleaks Secret Scan ==='
if (Get-Command gitleaks -ErrorAction SilentlyContinue) {
    gitleaks detect -s $CodeDir -v --report-path "reports/gitleaks_$(Split-Path $CodeDir -Leaf).txt" || $true
} else { Write-Warning 'gitleaks not installed. Skipping secrets scan.' }

Write-Host '=== 20. Grype Container Scan ==='
if ($DockerImage -and (Get-Command grype -ErrorAction SilentlyContinue)) {
    grype $DockerImage -o table > "reports/grype_${SafeImage}.txt"
} else { Write-Warning 'grype not installed or no image specified. Skipping grype scan.' }

Write-Host '=== 21. ClamAV Malware Scan ==='
if (Get-Command clamscan -ErrorAction SilentlyContinue) {
    clamscan -r $CodeDir > "reports/clamscan_$(Split-Path $CodeDir -Leaf).txt"
} else { Write-Warning 'clamscan not installed. Skipping malware scan.' }

Write-Host '=== 22. Rkhunter Rootkit Check ==='
if (Get-Command rkhunter -ErrorAction SilentlyContinue) {
    rkhunter --check --sk --rwo > "reports/rkhunter_${SafeTarget}.txt" || $true
} else { Write-Warning 'rkhunter not installed. Skipping rootkit check.' }

Write-Host '=== 23. Chkrootkit Rootkit Check ==='
if (Get-Command chkrootkit -ErrorAction SilentlyContinue) {
    chkrootkit > "reports/chkrootkit_${SafeTarget}.txt"
} else { Write-Warning 'chkrootkit not installed. Skipping rootkit check.' }

Write-Host '=== 24. Sublist3r Subdomain Enumeration ==='
if (Get-Command sublist3r -ErrorAction SilentlyContinue) {
    sublist3r -d $Target -o "reports/sublist3r_${SafeTarget}.txt"
} else { Write-Warning 'sublist3r not installed. Skipping subdomain enumeration.' }

Write-Host '=== 25. pip-audit Dependency Scan ==='
if (Get-Command pip-audit -ErrorAction SilentlyContinue) {
    pip-audit -r requirements.txt -f plain > "reports/pip_audit.txt" || $true
} else { Write-Warning 'pip-audit not installed. Skipping Python dependency audit.' }

Write-Host '=== 26. Nuclei Vulnerability Scanner ==='
if (Get-Command nuclei -ErrorAction SilentlyContinue) {
    nuclei -u $WebUrl -o "reports/nuclei_${SafeWeb}.txt" -silent
} else { Write-Warning 'nuclei not installed. Skipping Nuclei scan.' }

Write-Host '=== 27. Feroxbuster Advanced Web Fuzzer ==='
if (Get-Command feroxbuster -ErrorAction SilentlyContinue) {
    feroxbuster -u $WebUrl -w "$Env:USERPROFILE\seclists\Discovery\Web-Content\common.txt" `
        -o "reports/feroxbuster_${SafeWeb}.txt" --quiet || $true
} else { Write-Warning 'feroxbuster not installed. Skipping advanced fuzzing.' }

Write-Host '=== 28. Katana Web Crawler ==='
if (Get-Command katana -ErrorAction SilentlyContinue) {
    katana -u $WebUrl -o "reports/katana_${SafeWeb}.txt" -silent || $true
} else { Write-Warning 'katana not installed. Skipping web crawling.' }

Write-Host '=== 29. HTTPX HTTP Toolkit ==='
if (Get-Command httpx -ErrorAction SilentlyContinue) {
    echo $WebUrl | httpx -silent -tech-detect -status-code -title `
        -o "reports/httpx_${SafeWeb}.txt" || $true
} else { Write-Warning 'httpx not installed. Skipping HTTP analysis.' }

Write-Host '=== 30. Dalfox XSS Scanner ==='
if (Get-Command dalfox -ErrorAction SilentlyContinue) {
    dalfox url $WebUrl -o "reports/dalfox_${SafeWeb}.txt" --silence || $true
} else { Write-Warning 'dalfox not installed. Skipping XSS scanning.' }

Write-Host '=== 31. Amass Subdomain/Asset Discovery ==='
if (Get-Command amass -ErrorAction SilentlyContinue) {
    amass enum -passive -d $Target -o "reports/amass_${SafeTarget}.txt" || $true
} else { Write-Warning 'amass not installed. Skipping subdomain discovery.' }

Write-Host '=== 32. Semgrep Code Security Analysis ==='
if ((Get-Command semgrep -ErrorAction SilentlyContinue) -and (Test-Path $CodeDir)) {
    semgrep --config=auto $CodeDir --json -o "reports/semgrep_$(Split-Path $CodeDir -Leaf).json" || $true
} else { Write-Warning 'semgrep not installed or no code directory. Skipping semgrep scan.' }

Write-Host '=== 33. Snyk Security Testing ==='
if ((Get-Command snyk -ErrorAction SilentlyContinue) -and (Test-Path $CodeDir)) {
    Push-Location $CodeDir
    snyk test --json-file-output="$(Get-Location)\reports\snyk_$(Split-Path $CodeDir -Leaf).json" || $true
    Pop-Location
} else { Write-Warning 'snyk not installed or no code directory. Skipping Snyk scan.' }

Write-Host '=== 34. Safety Python Package Scanner ==='
if (Get-Command safety -ErrorAction SilentlyContinue) {
    safety check --json -o "reports/safety_check.json" || $true
} else { Write-Warning 'safety not installed. Skipping Safety scan.' }

Write-Host '=== 35. Syft SBOM Generator ==='
if ($DockerImage -and (Get-Command syft -ErrorAction SilentlyContinue)) {
    syft $DockerImage -o json > "reports/syft_${SafeImage}.json" || $true
} else { Write-Warning 'syft not installed or no image specified. Skipping SBOM generation.' }

Write-Host '=== 36. Static Security Configuration Checks ==='
if ((Get-Command python -ErrorAction SilentlyContinue) -and (Test-Path 'scripts/security/run_static_security_checks.py')) {
    python scripts/security/run_static_security_checks.py *> "reports/static_security_checks.txt" || $true
} else { Write-Warning 'python or static security checks script not found. Skipping.' }
if ((Get-Command python -ErrorAction SilentlyContinue) -and (Test-Path 'scripts/security/verify_dependencies.py')) {
    python scripts/security/verify_dependencies.py *> "reports/dependency_verify.txt" || $true
} else { Write-Warning 'python or dependency verification script not found. Skipping.' }

Write-Host '=== 37. API Security Test Suite ==='
if ($ApiBaseUrl -and (Test-Path 'scripts/windows/api_security_test.ps1')) {
    .\scripts\windows\api_security_test.ps1 -BaseUrl $ApiBaseUrl -OpenApiSpec $OpenApiSpecUrl || $true
} else { Write-Warning 'API base URL or api_security_test.ps1 missing. Skipping API tests.' }

Write-Host '=== 38. LLM Prompt Injection Tests ==='
if ($LlmEndpoint -and (Test-Path 'scripts/windows/llm_prompt_injection_test.ps1')) {
    .\scripts\windows\llm_prompt_injection_test.ps1 -ApiEndpoint $LlmEndpoint -AuthToken $LlmAuthToken || $true
} else { Write-Warning 'LLM endpoint or llm_prompt_injection_test.ps1 missing. Skipping LLM tests.' }

Write-Host '=== 39. AI-Driven Scan Correlation ==='
if ((Get-Command python -ErrorAction SilentlyContinue) -and (Test-Path 'scripts/windows/ai_driven_security_test.py')) {
    $provider = $env:AI_SECURITY_PROVIDER
    if (-not $provider) { $provider = 'local' }
    python scripts/windows/ai_driven_security_test.py --reports-dir reports --provider $provider --output reports/ai_analysis.txt || $true
} else { Write-Warning 'python or ai_driven_security_test.py missing. Skipping AI analysis.' }

Write-Host "Reports saved in the 'reports' directory. Review them for potential issues." -ForegroundColor Green
