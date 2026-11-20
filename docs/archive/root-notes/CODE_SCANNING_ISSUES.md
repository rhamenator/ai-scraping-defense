# Code Scanning Issues Report
Total findings: 38
Unique issue types: 6


## [Codacy] B104: hardcoded_bind_all_interfaces (2 occurrences, Severity: MEDIUM)
## Security Issue: hardcoded_bind_all_interfaces (B104)

**Severity:** MEDIUM
**Confidence:** MEDIUM

### Description
Possible binding to all interfaces.

### Affected Locations
Found in 2 location(s):

- `src/iis_gateway/main.py:184`
- `src/util/suricata_manager.py:40`

### More Information
https://bandit.readthedocs.io/en/1.9.1/plugins/b104_hardcoded_bind_all_interfaces.html

### Remediation
Please review the affected code and apply appropriate fixes based on the security guidelines.

---

## [Codacy] B110: try_except_pass (7 occurrences, Severity: LOW)
## Security Issue: try_except_pass (B110)

**Severity:** LOW
**Confidence:** HIGH

### Description
Try, Except, Pass detected.

### Affected Locations
Found in 7 location(s):

- `src/ai_service/alerts.py:300`
- `src/cloud_dashboard/cloud_dashboard_api.py:137`
- `src/escalation/escalation_engine.py:353`
- `src/escalation/escalation_engine.py:448`
- `src/escalation/escalation_engine.py:467`
- `src/shared/mcp_client.py:345`
- `src/shared/mcp_client.py:350`

### More Information
https://bandit.readthedocs.io/en/1.9.1/plugins/b110_try_except_pass.html

### Remediation
Please review the affected code and apply appropriate fixes based on the security guidelines.

**Specific Guidance for B110 (try-except-pass):**
- Consider logging the exception or handling it more explicitly
- If the exception is truly expected and can be ignored, add a comment explaining why
- Consider using more specific exception types instead of bare `except Exception:`

---

## [Codacy] B112: try_except_continue (2 occurrences, Severity: LOW)
## Security Issue: try_except_continue (B112)

**Severity:** LOW
**Confidence:** HIGH

### Description
Try, Except, Continue detected.

### Affected Locations
Found in 2 location(s):

- `src/rag/training.py:317`
- `src/rag/training.py:337`

### More Information
https://bandit.readthedocs.io/en/1.9.1/plugins/b112_try_except_continue.html

### Remediation
Please review the affected code and apply appropriate fixes based on the security guidelines.

---

## [Codacy] B311: blacklist (23 occurrences, Severity: LOW)
## Security Issue: blacklist (B311)

**Severity:** LOW
**Confidence:** HIGH

### Description
Standard pseudo-random generators are not suitable for security/cryptographic purposes.

### Affected Locations
Found in 23 location(s):

- `src/tarpit/bad_api_generator.py:42`
- `src/tarpit/bad_api_generator.py:49`
- `src/tarpit/bad_api_generator.py:50`
- `src/tarpit/js_zip_generator.py:61`
- `src/tarpit/js_zip_generator.py:73`
- `src/tarpit/js_zip_generator.py:74`
- `src/tarpit/js_zip_generator.py:75`
- `src/tarpit/js_zip_generator.py:108`
- `src/tarpit/js_zip_generator.py:117`
- `src/tarpit/js_zip_generator.py:120`

... and 13 more occurrences

### More Information
https://bandit.readthedocs.io/en/1.9.1/blacklists/blacklist_calls.html#b311-random

### Remediation
Please review the affected code and apply appropriate fixes based on the security guidelines.

---

## [Codacy] B404: blacklist (2 occurrences, Severity: LOW)
## Security Issue: blacklist (B404)

**Severity:** LOW
**Confidence:** HIGH

### Description
Consider possible security implications associated with the subprocess module.

### Affected Locations
Found in 2 location(s):

- `src/util/rules_fetcher/fetcher.py:3`
- `src/util/waf_manager.py:3`

### More Information
https://bandit.readthedocs.io/en/1.9.1/blacklists/blacklist_imports.html#b404-import-subprocess

### Remediation
Please review the affected code and apply appropriate fixes based on the security guidelines.

---

## [Codacy] B603: subprocess_without_shell_equals_true (2 occurrences, Severity: LOW)
## Security Issue: subprocess_without_shell_equals_true (B603)

**Severity:** LOW
**Confidence:** HIGH

### Description
subprocess call - check for execution of untrusted input.

### Affected Locations
Found in 2 location(s):

- `src/util/rules_fetcher/fetcher.py:60`
- `src/util/waf_manager.py:40`

### More Information
https://bandit.readthedocs.io/en/1.9.1/plugins/b603_subprocess_without_shell_equals_true.html

### Remediation
Please review the affected code and apply appropriate fixes based on the security guidelines.

---
