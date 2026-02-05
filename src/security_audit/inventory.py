"""Utilities to produce prioritized security inventories from JSON data."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

SEVERITY_ORDER: Mapping[str, int] = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "info": 1,
}


@dataclass
class InventoryItem:
    id: Optional[str] = None
    title: Optional[str] = None
    severity: str = "info"
    metadata: Dict[str, Any] = field(default_factory=dict)


def _normalize_severity(raw: Any) -> str:
    if raw is None:
        return "info"
    s = str(raw).strip().lower()
    # normalize common variants
    if s in ("crit", "critcal"):
        return "critical"
    if s == "":
        return "info"
    return s


def load_json(source: str | Path) -> Any:
    """Load JSON from a file path or from a JSON string."""
    text = str(source)
    # Heuristic: if it looks like a filename, read file
    if ("\n" not in text) and Path(text).exists():
        with Path(text).open("r", encoding="utf-8") as fh:
            return json.load(fh)
    # Otherwise assume it's a JSON string
    return json.loads(text)


def _as_item(obj: Mapping[str, Any]) -> InventoryItem:
    # Best-effort mapping of common keys
    id_ = obj.get("id") or obj.get("key") or obj.get("name")
    title = (
        obj.get("title") or obj.get("problem") or obj.get("name") or obj.get("summary")
    )
    severity = _normalize_severity(
        obj.get("severity") or obj.get("level") or obj.get("risk")
    )
    metadata = dict(obj)
    return InventoryItem(id=id_, title=title, severity=severity, metadata=metadata)


def extract_findings(
    parsed_json: Any,
    *,
    keys: Sequence[str] = ("findings", "vulnerabilities", "items", "problems"),
) -> List[InventoryItem]:
    """
    Extract a list of InventoryItem from parsed JSON.
    Looks for common container keys; if top-level list is provided it is used directly.
    """
    if parsed_json is None:
        return []

    if isinstance(parsed_json, list):
        return [_as_item(x) for x in parsed_json if isinstance(x, Mapping)]

    if isinstance(parsed_json, Mapping):
        for k in keys:
            val = parsed_json.get(k)
            if isinstance(val, list):
                return [_as_item(x) for x in val if isinstance(x, Mapping)]
        # Fallback: find the first list of mappings in values
        for val in parsed_json.values():
            if isinstance(val, list) and val and isinstance(val[0], Mapping):
                return [_as_item(x) for x in val if isinstance(x, Mapping)]
            # Recursively search nested dicts for the keys
            if isinstance(val, Mapping):
                for k in keys:
                    nested_val = val.get(k)
                    if isinstance(nested_val, list):
                        return [
                            _as_item(x) for x in nested_val if isinstance(x, Mapping)
                        ]

    return []


def prioritize_findings(items: Iterable[InventoryItem]) -> List[InventoryItem]:
    """Return items sorted by severity (highest first)."""
    return sorted(
        items, key=lambda it: SEVERITY_ORDER.get(it.severity, 0), reverse=True
    )


def summarize_by_severity(items: Iterable[InventoryItem]) -> Dict[str, int]:
    """Return a mapping of severity -> count."""
    c: Counter[str] = Counter()
    for it in items:
        c[it.severity or "info"] += 1
    return dict(c)


def generate_inventory_markdown(data: Any) -> str:
    """
    Generate a simple markdown report for an inventory.

    Accepts either:
      - an iterable of InventoryItem, or
      - a parsed JSON object that extract_findings() can handle,
      - or a JSON string / path that load_json() can handle.

    Returns a markdown string summarizing counts by severity and a small table.
    """
    # Normalize input to InventoryItem list
    items: List[InventoryItem] = []
    try:
        if isinstance(data, list) and data and isinstance(data[0], InventoryItem):
            items = list(data)
        else:
            parsed = data
            if not isinstance(parsed, (list, dict)):
                # assume it's JSON string or a filepath
                try:
                    parsed = load_json(parsed)
                except Exception:
                    parsed = None
            items = extract_findings(parsed)
    except Exception:
        # As a last resort, return an informative markdown
        return "# Inventory\n\n_Error generating inventory report_\n"

    if not items:
        return "# Inventory\n\n_No findings_\n"

    # Summary header
    counts = summarize_by_severity(items)
    header_lines = ["# Inventory", ""]
    header_lines.append("## Summary by severity")
    for sev, cnt in sorted(
        counts.items(), key=lambda kv: SEVERITY_ORDER.get(kv[0], 0), reverse=True
    ):
        header_lines.append(f"- **{sev}**: {cnt}")
    header_lines.append("")

    # Small table of top items (prioritized)
    prioritized = prioritize_findings(items)
    header_lines.append("## Top findings")
    header_lines.append("| id | title | severity |")
    header_lines.append("|---|---|---|")
    for it in prioritized[:20]:
        id_text = it.id or ""
        title_text = (it.title or "").replace("|", "\\|")
        header_lines.append(f"| {id_text} | {title_text} | {it.severity} |")

    return "\n".join(header_lines) + "\n"


__all__ = [
    "InventoryItem",
    "load_json",
    "extract_findings",
    "prioritize_findings",
    "summarize_by_severity",
    "generate_inventory_markdown",
]
