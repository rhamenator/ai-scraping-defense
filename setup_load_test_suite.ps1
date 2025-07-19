param()
$ErrorActionPreference = 'Stop'
Write-Host '=== Installing load testing tools ===' -ForegroundColor Cyan

$pkgManager = $null
if (Get-Command apt-get -ErrorAction SilentlyContinue) { $pkgManager = 'apt-get' }
elseif (Get-Command yum -ErrorAction SilentlyContinue) { $pkgManager = 'yum' }
else { Write-Error 'Unsupported package manager. Install wrk, siege, and apache2-utils manually.'; exit 1 }

sudo $pkgManager update -y
sudo $pkgManager install -y wrk siege apache2-utils

if (-not (Get-Command k6 -ErrorAction SilentlyContinue)) {
    Write-Host 'Installing k6...'
    if ($pkgManager -eq 'apt-get') {
        sudo apt-get install -y gnupg2 curl
        curl -fsSL https://dl.k6.io/key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/k6-archive-keyring.gpg
        echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
        sudo apt-get update
        sudo apt-get install -y k6
    } else {
        sudo yum install -y k6
    }
}

if (-not (Get-Command locust -ErrorAction SilentlyContinue)) {
    pip install --user locust
}

@'
Load testing tools installed.
Example commands:
  wrk -t4 -c100 -d30s http://localhost:8080
  siege -c50 -t1m http://localhost:8080
  ab -n 1000 -c100 http://localhost:8080/
  k6 run examples/script.js
  locust -f examples/locustfile.py

Ensure you have permission before running tests.
'@ | Write-Host
