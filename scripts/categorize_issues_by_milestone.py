"""Generate milestone assignments for problem map entries."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

DEFAULT_INPUT = Path("problem_file_map.json")
DEFAULT_OUTPUT = Path("issue_milestone_assignments.json")

MILESTONE_SEQUENCE = [
    "Local Stability",
    "Local Network Deployment",
    "Security Testing",
    "Deployment Readiness",
    "Cloud Test",
    "Production Readiness",
    "Feature Enhancements",
    "Untriaged",
]

PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}

SECURITY_KEYWORDS = {
    "csrf",
    "xss",
    "sql injection",
    "brute force",
    "vulnerab",
    "cve",
    "exploit",
    "malicious",
    "threat",
    "attack",
}

LOCAL_STABILITY_KEYWORDS = {
    "docker-compose up",
    "container startup",
    "startup error",
    "startup failure",
    "boot failure",
    "routing failure",
    "routing issue",
    "localhost",
    "env misconfig",
    ".env",
}

NETWORK_KEYWORDS = {
    "lan",
    "firewall",
    "local network",
    "multi-device",
    "ip exposure",
    "port forwarding",
    "vpn",
    "network access",
}

DEPLOYMENT_KEYWORDS = {
    "dockerfile",
    "docker-compose",
    ".ebextensions",
    "packaging",
    "deployment",
    "aws env",
    "bundle",
    "helm chart",
    "terraform",
}

CLOUD_KEYWORDS = {
    "elastic beanstalk",
    "aws",
    "cloudfront",
    "free tier",
    "endpoint validation",
    "cloud test",
    "s3",
}

PRODUCTION_KEYWORDS = {
    "ssl",
    "scal",
    "monitor",
    "observability",
    "ci/cd",
    "compliance",
    "performance",
    "hardening",
    "slo",
    "sli",
    "metrics",
    "logging",
    "alert",
    "automation",
    "kubernetes",
    "redis",
    "postgres",
}

FEATURE_KEYWORDS = {
    "ui",
    "ux",
    "documentation",
    "docs",
    "logging refinement",
    "developer experience",
    "dx",
    "refactor",
    "code quality",
    "plugin",
    "feature",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to problem_file_map.json",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT, help="Destination JSON file"
    )
    return parser.parse_args()


def choose_milestone(
    record: Dict[str, object], text_blob: str, severity: str
) -> Tuple[str, str]:
    category = str(record.get("category") or "").strip()

    if category.lower() == "security" or any(
        term in text_blob for term in SECURITY_KEYWORDS
    ):
        return "Security Testing", "Security-focused issue routed to Security Testing."

    if any(term in text_blob for term in LOCAL_STABILITY_KEYWORDS):
        return "Local Stability", "Affects local startup or environment stability."

    if any(term in text_blob for term in NETWORK_KEYWORDS):
        return (
            "Local Network Deployment",
            "Network exposure or LAN configuration matter.",
        )

    if any(term in text_blob for term in DEPLOYMENT_KEYWORDS):
        return (
            "Deployment Readiness",
            "Packaging or deployment configuration referenced.",
        )

    if any(term in text_blob for term in CLOUD_KEYWORDS):
        return "Cloud Test", "Cloud validation or AWS context detected."

    if category in {"Operations", "Compliance", "Performance"}:
        return (
            "Production Readiness",
            f"{category} improvements align with production hardening.",
        )

    if any(term in text_blob for term in PRODUCTION_KEYWORDS):
        return (
            "Production Readiness",
            "Scaling, monitoring, or production hardening keywords present.",
        )

    if category == "Architecture":
        return (
            "Production Readiness",
            "Architecture change supporting production readiness.",
        )

    if category == "Code Quality" or any(
        term in text_blob for term in FEATURE_KEYWORDS
    ):
        return "Feature Enhancements", "Code quality or enhancement oriented work."

    return "Untriaged", "No rule matched; requires manual triage."


def format_reason(base: str, severity: str, confidence: float | None) -> str:
    reason = f"{base} Severity {severity}."
    if isinstance(confidence, (int, float)):
        reason += f" Confidence {confidence:.2f}."
    return reason


def main() -> int:
    args = parse_args()

    if not args.input.exists():
        print(f"Input file {args.input} not found.", file=sys.stderr)
        return 1

    with args.input.open("r", encoding="utf-8") as handle:
        problem_map = json.load(handle)

    assignments: List[Dict[str, object]] = []

    for title, payload in problem_map.items():
        severity_raw = (payload.get("severity") or "Medium").title()
        severity = severity_raw if severity_raw in PRIORITY_ORDER else "Medium"
        confidence = payload.get("confidence")

        text_blob_parts = [
            title,
            payload.get("fix_prompt") or "",
            " ".join(payload.get("original_affected") or []),
            " ".join(payload.get("resolved_files") or []),
        ]
        text_blob = "\n".join(text_blob_parts).lower()

        milestone, base_reason = choose_milestone(payload, text_blob, severity)
        reason = format_reason(base_reason, severity, confidence)

        assignments.append(
            {
                "issue_id": title,
                "milestone": milestone,
                "priority": severity,
                "reason": reason,
                "confidence": (
                    confidence if isinstance(confidence, (int, float)) else None
                ),
            }
        )

    milestone_rank = {name: index for index, name in enumerate(MILESTONE_SEQUENCE)}

    def sort_key(entry: Dict[str, object]) -> Tuple[int, int, float]:
        milestone_index = milestone_rank.get(
            entry["milestone"], len(MILESTONE_SEQUENCE)
        )
        priority_index = PRIORITY_ORDER.get(entry["priority"], 1)
        confidence_value = (
            entry["confidence"]
            if isinstance(entry["confidence"], (int, float))
            else -1.0
        )
        return milestone_index, priority_index, -confidence_value

    assignments.sort(key=sort_key)

    for item in assignments:
        item.pop("confidence", None)

    args.output.write_text(json.dumps(assignments, indent=2), encoding="utf-8")
    print(f"Wrote {len(assignments)} assignments to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
