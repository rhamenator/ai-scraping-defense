"""Utilities to produce prioritized security inventories from JSON data."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

PRIORITY_RULES: Sequence[tuple[str, tuple[str, ...]]] = (
    ("Critical (Secrets)", ("secret", "credential", "password", "api key", "token")),
    (
        "High (Transport Security)",
        ("https", "tls", "transport", "ssl", "hsts", "certificate"),
    ),
    (
        "High (Authentication/Authorization)",
        ("auth", "jwt", "rbac", "session", "mfa", "authorization"),
    ),
)
PRIORITY_ORDER = {label: index for index, (label, _) in enumerate(PRIORITY_RULES)}
DEFAULT_PRIORITY = "Medium (General Hardening)"
TARGET_PREFIXES = ("src/", "scripts/", "nginx/")
TARGET_FILES = {"docker-compose.yaml"}


@dataclass
class InventoryItem:
    """Represents a single security finding from the batch file."""

    identifier: int
    problem: str
    fix_prompt: str
    affected_files: list[str]
    priority: str

    @property
    def area(self) -> str:
        root = sorted({_derive_area(path) for path in self.affected_files})
        return ", ".join(root) if root else "n/a"


def _derive_area(path: str) -> str:
    if path == "docker-compose.yaml":
        return "docker-compose"
    return path.split("/", 1)[0]


def _normalize_path(raw: str) -> str:
    return raw.split(":", 1)[0]


def _is_target_path(path: str) -> bool:
    if path in TARGET_FILES:
        return True
    return any(path.startswith(prefix) for prefix in TARGET_PREFIXES)


def _determine_priority(problem: str, fix_prompt: str) -> str:
    haystack = f"{problem} {fix_prompt}".lower()
    for label, keywords in PRIORITY_RULES:
        if any(keyword in haystack for keyword in keywords):
            return label
    return DEFAULT_PRIORITY


def _filter_items(raw_items: Iterable[dict]) -> List[InventoryItem]:
    filtered: List[InventoryItem] = []
    for entry in raw_items:
        affected = [_normalize_path(path) for path in entry.get("affected_files", [])]
        scoped = [path for path in affected if _is_target_path(path)]
        if not scoped:
            continue
        priority = _determine_priority(entry.get("problem", ""), entry.get("fix_prompt", ""))
        filtered.append(
            InventoryItem(
                identifier=int(entry.get("id")),
                problem=entry.get("problem", "Unknown problem"),
                fix_prompt=entry.get("fix_prompt", ""),
                affected_files=sorted(set(scoped)),
                priority=priority,
            )
        )
    return filtered


def _sort_items(items: Sequence[InventoryItem]) -> List[InventoryItem]:
    def sort_key(item: InventoryItem) -> tuple[int, int]:
        priority_rank = PRIORITY_ORDER.get(item.priority, len(PRIORITY_ORDER))
        return (priority_rank, item.identifier)

    return sorted(items, key=sort_key)


def generate_inventory_markdown(json_path: Path) -> str:
    """Generate a markdown table with prioritized issues from the JSON file."""

    data = json.loads(json_path.read_text())
    problems = data.get("security_problems", {}).get("problems", [])
    items = _filter_items(problems)
    if not items:
        return "# Security Inventory – Batch 1\n\nNo scoped issues were detected."

    items = _sort_items(items)

    counts = Counter(item.priority for item in items)
    summary_lines = ["## Prioritization Summary\n"]
    for label, _ in PRIORITY_RULES:
        if label in counts:
            summary_lines.append(f"- **{label}:** {counts[label]} findings")
    if DEFAULT_PRIORITY in counts:
        summary_lines.append(f"- **{DEFAULT_PRIORITY}:** {counts[DEFAULT_PRIORITY]} findings")

    header = [
        "# Security Inventory – Batch 1",
        "",
        "This report inventories findings from `security_problems_batch1.json`",
        "with scope limited to `src/`, `scripts/`, `nginx/`, and `docker-compose.yaml`.",
        "Findings are prioritized by exploitability, emphasizing secrets, transport",
        "security, and authentication/authorization weaknesses.",
        "",
    ]

    table_header = (
        "| Priority | ID | Area | Problem | Key Files | Recommended Actions |\n"
        "| --- | --- | --- | --- | --- | --- |"
    )
    rows = []
    for item in items:
        key_files = "<br/>".join(item.affected_files)
        fix_prompt = re.sub(r"\s+", " ", item.fix_prompt.strip())
        row = (
            f"| {item.priority} | {item.identifier} | {item.area} | {item.problem} | "
            f"{key_files} | {fix_prompt} |"
        )
        rows.append(row)

    body = ["## Detailed Findings", "", table_header, *rows]

    return "\n".join(header + summary_lines + [""] + body) + "\n"


def write_inventory_markdown(json_path: Path, output_path: Path) -> None:
    """Write the generated markdown inventory to disk."""

    markdown = generate_inventory_markdown(json_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown)


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    write_inventory_markdown(
        Path("security_problems_batch1.json"),
        Path("docs/security/security_inventory_batch1.md"),
    )
