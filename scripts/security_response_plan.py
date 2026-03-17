"""Shared security response planning for alert-driven automation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

SEVERITY_RANK = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


@dataclass(frozen=True)
class ResponsePlanEntry:
    source: str
    dedupe_key: str
    title: str
    severity: str
    occurrences: int
    create_issue: bool
    page_operator: bool
    automated_response: str | None
    rationale: str


def normalize_severity(raw_value: str | None) -> str:
    value = str(raw_value or "").strip().lower()
    if value in {"", "unknown"}:
        return "low"
    if value in {"moderate", "warning"}:
        return "medium"
    if value == "error":
        return "high"
    if value in SEVERITY_RANK:
        return value
    return "low"


def build_response_plan_entry(
    *,
    source: str,
    dedupe_key: str,
    title: str,
    severity: str,
    occurrences: int,
) -> ResponsePlanEntry:
    normalized_severity = normalize_severity(severity)

    if source == "secret_scanning":
        return ResponsePlanEntry(
            source=source,
            dedupe_key=dedupe_key,
            title=title,
            severity="critical",
            occurrences=occurrences,
            create_issue=True,
            page_operator=True,
            automated_response="rotate_credentials",
            rationale=(
                "Secret exposure needs immediate operator attention, credential "
                "rotation, and a tracked remediation issue."
            ),
        )

    if source == "dependabot":
        return ResponsePlanEntry(
            source=source,
            dedupe_key=dedupe_key,
            title=title,
            severity=normalized_severity,
            occurrences=occurrences,
            create_issue=SEVERITY_RANK[normalized_severity] >= SEVERITY_RANK["medium"],
            page_operator=normalized_severity == "critical",
            automated_response=(
                "expedite_patch" if normalized_severity == "critical" else None
            ),
            rationale=(
                "Dependabot alerts create backlog work at medium+ severity, while "
                "critical advisories page operators for expedited patching."
            ),
        )

    if source == "code_scanning":
        return ResponsePlanEntry(
            source=source,
            dedupe_key=dedupe_key,
            title=title,
            severity=normalized_severity,
            occurrences=occurrences,
            create_issue=SEVERITY_RANK[normalized_severity] >= SEVERITY_RANK["medium"],
            page_operator=normalized_severity == "critical",
            automated_response=(
                "expedite_hotfix" if normalized_severity == "critical" else None
            ),
            rationale=(
                "Code scanning findings become tracked work at medium+ severity, "
                "while critical findings require operator paging and hotfix review."
            ),
        )

    return ResponsePlanEntry(
        source=source,
        dedupe_key=dedupe_key,
        title=title,
        severity=normalized_severity,
        occurrences=occurrences,
        create_issue=False,
        page_operator=False,
        automated_response=None,
        rationale="No automation policy is defined for this source type.",
    )


def summarize_response_plan(entries: Iterable[ResponsePlanEntry]) -> dict[str, object]:
    entry_list = list(entries)
    by_source: dict[str, dict[str, int]] = {}
    for entry in entry_list:
        source_counts = by_source.setdefault(
            entry.source,
            {
                "total_groups": 0,
                "issues": 0,
                "operator_pages": 0,
                "automated_responses": 0,
            },
        )
        source_counts["total_groups"] += 1
        source_counts["issues"] += int(entry.create_issue)
        source_counts["operator_pages"] += int(entry.page_operator)
        source_counts["automated_responses"] += int(
            entry.automated_response is not None
        )

    return {
        "total_groups": len(entry_list),
        "issues": sum(int(entry.create_issue) for entry in entry_list),
        "operator_pages": sum(int(entry.page_operator) for entry in entry_list),
        "automated_responses": sum(
            int(entry.automated_response is not None) for entry in entry_list
        ),
        "by_source": by_source,
    }


def build_plan_payload(
    *,
    repository: str,
    mode: str,
    entries: Iterable[ResponsePlanEntry],
) -> dict[str, object]:
    entry_list = list(entries)
    return {
        "repository": repository,
        "mode": mode,
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": summarize_response_plan(entry_list),
        "entries": [asdict(entry) for entry in entry_list],
    }


def write_plan_payload(path: str | Path, payload: dict[str, object]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
