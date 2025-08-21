import json
import os

counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0, "total": 0}


def add(sev, n=1):
    sev = (sev or "info").lower()
    sev = {
        "critical": "critical",
        "high": "high",
        "moderate": "medium",
        "medium": "medium",
        "low": "low",
        "info": "info",
    }.get(sev, "info")
    counts[sev] += n
    counts["total"] += n


def load_json(p):
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return {}


# Semgrep
d = load_json("reports/semgrep.json")
for r in d.get("results", []) or []:
    add(r.get("extra", {}).get("severity", "info"), 1)
# Gitleaks
d = load_json("reports/gitleaks.json")
findings = d.get("findings", d if isinstance(d, list) else [])
for _ in findings:
    add("high", 1)
# Trivy
for pth in ("reports/trivy-fs.json", "reports/trivy-config.json"):
    d = load_json(pth)
    for r in d.get("Results", []) or []:
        for v in r.get("Vulnerabilities") or []:
            add(v.get("Severity", "MEDIUM"), 1)
        for m in r.get("Misconfigurations") or []:
            add(m.get("Severity", "MEDIUM"), 1)
        for s in r.get("Secrets") or []:
            add("high", 1)
# Bandit
d = load_json("reports/bandit.json")
for r in d.get("results", []) or []:
    add(r.get("issue_severity", "MEDIUM"), 1)
# pip-audit
d = load_json("reports/pip-audit.json")
for v in d.get("vulnerabilities", []) or []:
    add((v.get("severity") or "MEDIUM"), 1)
# npm audit (new schema tolerant)
d = load_json("reports/npm-audit.json")
vulns = d.get("vulnerabilities", {}) or {}
for name, info in vulns.items():
    sev = info.get("severity", "moderate")
    via = info.get("via", [])
    cnt = len([x for x in via if isinstance(x, dict)]) or 1
    add(sev, cnt)
# gosec
d = load_json("reports/gosec.json")
for i in d.get("Issues", []) or []:
    add(i.get("Severity", "MEDIUM"), 1)
# govulncheck (streamed json lines fallback)
try:
    with open("reports/govuln.json") as f:
        for ln in f:
            if '"vuln":' in ln:
                add("high", 1)
except FileNotFoundError:
    pass
# cargo-audit
d = load_json("reports/cargo-audit.json")
for v in d.get("vulnerabilities", {}).get("list", []) or []:
    sev = v.get("advisory", {}).get("cvss", {}).get("severity") or "HIGH"
    add(sev, 1)

# linters as low
for p in (
    "reports/hadolint.txt",
    "reports/shellcheck.txt",
    "reports/markdownlint.txt",
    "reports/yamllint.txt",
):
    if os.path.exists(p):
        n = sum(1 for _ in open(p))
        add("low", n)

print(json.dumps(counts, indent=2))
