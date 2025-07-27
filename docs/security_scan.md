# Security Scan Helper

`security_scan.sh` runs a collection of open-source tools to audit a target for common weaknesses. It invokes scanners such as **Nmap**, **Nikto**, **OWASP ZAP**, and **Trivy** alongside optional checks like **SQLMap** and **Bandit**.

## Prerequisites
- Linux environment with the required utilities installed (e.g. `nmap`, `nikto`, `zaproxy`, `trivy`, `sqlmap`, `masscan`, `bandit`, etc.)
- Many scans need elevated privileges; run the script with `sudo`.
- Optionally install Docker if container images will be scanned.

## Legal Considerations
Only run the script against systems you own or have explicit permission to test. Unauthorized scanning can be illegal and may violate service agreements. Always consult local laws and organizational policies before performing any security tests.
