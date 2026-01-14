"""Assign milestones to problem map entries and sync them with GitHub.

This script augments `problem_file_map.json` and `problem_file_map.db` with
milestone metadata that corresponds to GitHub milestones. It applies a mixture of
label, category, and severity heuristics to determine the appropriate milestone,
creates sub-milestones when additional prioritisation is helpful, and ensures
that matching milestones exist in the GitHub repository. The resulting milestone
number and HTML URL are written back to the JSON and SQLite artefacts so that
other automation can reference them.

Run from the repository root:

    python scripts/update_problem_milestones.py

Environment variables:
    GITHUB_TOKEN       Personal access token or workflow token with `repo`
                       scope. Required to create milestones or fetch private
                       metadata. If absent, the script performs a local-only
                       update.
    GITHUB_REPOSITORY  Optional `owner/repo` override (defaults to
                       `rhamenator/ai-scraping-defense`).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests

# === CONFIG ===
DEFAULT_JSON_FILE = Path("problem_file_map.json")
DEFAULT_DB_FILE = Path("problem_file_map.db")
DEFAULT_OWNER = "rhamenator"
DEFAULT_REPO = "ai-scraping-defense"
CATEGORY_THRESHOLD_FOR_FOCUS = 20

# === BASE MILESTONES ===
BASE_MILESTONES = {
    "Local Stability": "Stabilise the local developer and test experience.",
    "Local Network Deployment": "Prepare LAN-focused deployment hardening.",
    "Security Testing": "Execute targeted security validation work.",
    "Deployment Readiness": "Improve deployment automation and packaging.",
    "Cloud Test": "Validate the stack against cloud integration targets.",
    "Production Readiness": "Close gaps required for production roll-out.",
    "Feature Enhancements": "Track product and DX enhancements.",
}

# === LABEL → MILESTONE MATRIX ===
LABEL_TO_MILESTONE = {
    "bug": "Local Stability",
    "network": "Local Network Deployment",
    "security": "Security Testing",
    "deployment": "Deployment Readiness",
    "cloud-test": "Cloud Test",
    "production": "Production Readiness",
    "enhancement": "Feature Enhancements",
    "documentation": "Feature Enhancements",
    "infra": "Production Readiness",
}

# === LOGGER ===
LOG = logging.getLogger("update_problem_milestones")
MILESTONE_PREFIX_RE = re.compile(r"^\s*(\d+)\.\s*(.+)$")


def normalize_milestone_title(title: str) -> str:
    match = MILESTONE_PREFIX_RE.match(title)
    if match:
        return match.group(2).strip()
    return title.strip()


def extract_milestone_prefix(title: str) -> Optional[str]:
    match = MILESTONE_PREFIX_RE.match(title)
    if match:
        return f"{match.group(1)}."
    return None


def milestone_base_title(title: str) -> str:
    normalized = normalize_milestone_title(title)
    return normalized.split(" :: ", 1)[0].strip()


@dataclass
class MilestoneInfo:
    """Metadata for a GitHub milestone."""

    title: str
    number: Optional[int]
    url: Optional[str]
    state: str = "open"
    parent: Optional[str] = None


class GitHubMilestoneManager:
    """Fetch and create milestones via the GitHub REST API."""

    def __init__(
        self,
        owner: str,
        repo: str,
        token: Optional[str],
        dry_run: bool = False,
    ) -> None:
        self.owner = owner
        self.repo = repo
        self.token = token
        self.dry_run = dry_run
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/vnd.github+json",
            "User-Agent": "problem-map-milestone-sync",
        })
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"
        self._cache: Dict[str, MilestoneInfo] = {}
        self._normalized_map: Dict[str, str] = {}
        self._prefix_map: Dict[str, str] = {}
        self._load_existing()

    # ------------------------------------------------------------------
    def _repo_url(self, suffix: str) -> str:
        return f"https://api.github.com/repos/{self.owner}/{self.repo}/{suffix}"

    def _load_existing(self) -> None:
        """Populate the cache with existing milestones."""
        page = 1
        while True:
            params = {"state": "all", "per_page": 100, "page": page}
            response = self._session.get(self._repo_url("milestones"), params=params, timeout=30)
            if response.status_code == 401:
                LOG.warning("GitHub authentication failed; continuing without API access.")
                self._cache.clear()
                return
            if response.status_code not in (200, 404):
                LOG.debug("GitHub response %s: %s", response.status_code, response.text)
            if response.status_code == 404:
                LOG.warning("Repository %s/%s not found or inaccessible.", self.owner, self.repo)
                self._cache.clear()
                return
            response.raise_for_status()
            payload = response.json()
            if not payload:
                break
            for milestone in payload:
                info = MilestoneInfo(
                    title=milestone["title"],
                    number=milestone["number"],
                    url=milestone.get("html_url"),
                    state=milestone.get("state", "open"),
                )
                self._cache[info.title] = info
                normalized = normalize_milestone_title(info.title)
                self._normalized_map.setdefault(normalized, info.title)
                prefix = extract_milestone_prefix(info.title)
                if prefix:
                    base = milestone_base_title(info.title)
                    self._prefix_map.setdefault(base, prefix)
            if "next" not in response.links:
                break
            page += 1
        LOG.info("Fetched %d existing GitHub milestones.", len(self._cache))

    # ------------------------------------------------------------------
    def ensure(self, title: str, description: str, parent: Optional[str]) -> MilestoneInfo:
        """Ensure a milestone exists, creating it if necessary."""
        resolved_parent = self.resolve_title(parent) if parent else None
        resolved_title = self.resolve_title(title)
        if resolved_title in self._cache:
            info = self._cache[resolved_title]
            info.parent = resolved_parent
            return info

        if not self.token or self.dry_run:
            display_title = self.format_title(title)
            LOG.info("Skipping GitHub creation for milestone '%s' (dry-run or missing token).", display_title)
            info = MilestoneInfo(title=display_title, number=None, url=None, parent=resolved_parent)
            self._cache[display_title] = info
            return info

        display_title = self.format_title(title)
        payload = {"title": display_title, "state": "open", "description": description}
        response = self._session.post(self._repo_url("milestones"), json=payload, timeout=30)
        if response.status_code == 422:
            # A concurrent actor may have created the milestone; refetch cache.
            LOG.info("Milestone '%s' already exists per GitHub; refreshing cache.", display_title)
            self._load_existing()
            info = self._cache.get(display_title) or self._cache.get(resolved_title)
            if info:
                info.parent = resolved_parent
                return info
            raise RuntimeError(f"Unable to resolve milestone '{display_title}' after 422 response.")
        response.raise_for_status()
        milestone = response.json()
        info = MilestoneInfo(
            title=milestone["title"],
            number=milestone["number"],
            url=milestone.get("html_url"),
            parent=resolved_parent,
        )
        self._cache[info.title] = info
        LOG.info("Created GitHub milestone '%s' (#%s).", info.title, info.number)
        return info

    def resolve_title(self, title: str) -> str:
        normalized = normalize_milestone_title(title)
        return self._normalized_map.get(normalized, title)

    def format_title(self, title: str) -> str:
        if extract_milestone_prefix(title):
            return title
        base = milestone_base_title(title)
        prefix = self._prefix_map.get(base)
        if prefix:
            return f"{prefix} {title}"
        return title


# === MILESTONE ASSIGNMENT LOGIC ===

def assign_base_milestone(record: Dict[str, object]) -> str:
    """Assign the primary milestone name before sub-categorisation."""
    category = str(record.get("category", ""))
    severity = str(record.get("severity", ""))
    labels = record.get("labels") or []

    for label in labels:
        if label in LABEL_TO_MILESTONE:
            return LABEL_TO_MILESTONE[label]

    if category in ("Operations", "Code Quality") and severity == "High":
        return "Local Stability"
    if category == "Architecture" and any(
        isinstance(item, str)
        and ("LAN" in item or "network" in item.lower())
        for item in record.get("original_affected", [])
    ):
        return "Local Network Deployment"
    if category == "Security":
        return "Security Testing"
    if category == "Architecture" and any(
        isinstance(item, str)
        and ("docker-compose" in item or item.endswith(".ebextensions"))
        for item in record.get("resolved_files", [])
    ):
        return "Deployment Readiness"
    if category == "Operations" and "Elastic Beanstalk" in str(record.get("fix_prompt", "")):
        return "Cloud Test"
    if category in ("Compliance", "Performance"):
        return "Production Readiness"
    return "Feature Enhancements"


def derive_sub_milestone(base: str, record: Dict[str, object]) -> Tuple[str, Optional[str]]:
    """Derive a sub-milestone name when additional prioritisation helps."""
    severity = str(record.get("severity", "")).strip()
    if not severity:
        return base, None
    sub_title = f"{base} :: {severity.title()}"
    if sub_title == base:
        return base, None
    return sub_title, base


def detect_focus_milestones(
    problems: Dict[str, Dict[str, object]],
    base_assignments: Dict[str, str],
    existing_milestones: Iterable[str],
    threshold: int,
) -> Dict[str, str]:
    """Create category focus milestones when counts exceed the threshold."""
    existing = set(existing_milestones)
    category_counts = Counter(record.get("category", "") for record in problems.values())
    category_focus: Dict[str, str] = {}

    for category, count in category_counts.items():
        if not category:
            continue
        focus_title = f"{category} Focus"
        if count >= threshold and focus_title not in existing:
            existing.add(focus_title)
            category_focus[category] = focus_title
            LOG.info("Added dynamic milestone '%s' for %s issues (count=%d).", focus_title, category, count)

    if not category_focus:
        return base_assignments

    updated = dict(base_assignments)
    for problem_id, record in problems.items():
        category = record.get("category")
        if category in category_focus:
            updated[problem_id] = category_focus[category]
    return updated


# === HELPERS ===

def apply_assignments(
    problems: Dict[str, Dict[str, object]],
    base_assignments: Dict[str, str],
) -> Dict[str, Dict[str, object]]:
    """Apply sub-milestone logic and collect per-milestone stats."""
    milestone_stats: Dict[str, Dict[str, object]] = defaultdict(
        lambda: {"count": 0, "categories": Counter(), "severities": Counter(), "parent": None}
    )

    for problem_id, base in base_assignments.items():
        record = problems[problem_id]
        final_title, parent = derive_sub_milestone(base, record)
        record["milestone"] = final_title
        record["milestone_parent"] = parent
        milestone_stats[final_title]["count"] += 1
        milestone_stats[final_title]["categories"][record.get("category", "Unknown")] += 1
        milestone_stats[final_title]["severities"][record.get("severity", "Unknown")] += 1
        milestone_stats[final_title]["parent"] = parent

    return milestone_stats


def format_description(title: str, stats: Dict[str, object]) -> str:
    """Build a helpful description for a milestone created automatically."""
    lines = [
        f"Autogenerated milestone '{title}' for problem map prioritisation.",
    ]
    parent = stats.get("parent")
    if parent:
        lines.append(f"Parent milestone: {parent}.")
    categories: Counter = stats.get("categories", Counter())
    if categories:
        top = ", ".join(f"{cat} ({count})" for cat, count in categories.most_common(3))
        lines.append(f"Top categories: {top}.")
    severities: Counter = stats.get("severities", Counter())
    if severities:
        top = ", ".join(f"{sev} ({count})" for sev, count in severities.most_common())
        lines.append(f"Severity mix: {top}.")
    lines.append("Managed by scripts/update_problem_milestones.py.")
    return " ".join(lines)


def update_database(
    db_path: Path,
    assignments: Dict[str, MilestoneInfo],
    problems: Dict[str, Dict[str, object]],
) -> None:
    if not db_path.exists():
        LOG.warning("Database %s not found; skipping DB sync.", db_path)
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(problems)")
    columns = {row[1] for row in cursor.fetchall()}

    alterations = []
    if "milestone" not in columns:
        alterations.append("ALTER TABLE problems ADD COLUMN milestone TEXT")
    if "milestone_parent" not in columns:
        alterations.append("ALTER TABLE problems ADD COLUMN milestone_parent TEXT")
    if "milestone_number" not in columns:
        alterations.append("ALTER TABLE problems ADD COLUMN milestone_number INTEGER")
    if "milestone_url" not in columns:
        alterations.append("ALTER TABLE problems ADD COLUMN milestone_url TEXT")

    for statement in alterations:
        cursor.execute(statement)

    for title, record in problems.items():
        milestone_title = record.get("milestone")
        milestone_parent = record.get("milestone_parent")
        info = assignments.get(milestone_title)
        milestone_number = info.number if info else None
        milestone_url = info.url if info else None
        cursor.execute(
            """
            UPDATE problems
            SET milestone = ?, milestone_parent = ?, milestone_number = ?, milestone_url = ?
            WHERE title = ?
            """,
            (milestone_title, milestone_parent, milestone_number, milestone_url, title),
        )

    conn.commit()
    conn.close()
    LOG.info("Updated SQLite database with milestone metadata.")


def parse_owner_repo(default_owner: str, default_repo: str) -> Tuple[str, str]:
    env_repo = os.environ.get("GITHUB_REPOSITORY")
    if env_repo and "/" in env_repo:
        owner, repo = env_repo.split("/", 1)
        return owner, repo
    return default_owner, default_repo


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON_FILE, help="Path to problem_file_map.json")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_FILE, help="Path to problem_file_map.db")
    parser.add_argument("--owner", type=str, default=None, help="GitHub repository owner")
    parser.add_argument("--repo", type=str, default=None, help="GitHub repository name")
    parser.add_argument("--token", type=str, default=os.environ.get("GITHUB_TOKEN"), help="GitHub token")
    parser.add_argument("--dry-run", action="store_true", help="Skip GitHub mutations and use placeholders")
    parser.add_argument(
        "--category-threshold",
        type=int,
        default=CATEGORY_THRESHOLD_FOR_FOCUS,
        help="Minimum issues per category before creating a dynamic focus milestone",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: INFO)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(message)s")

    json_path = args.json
    if not json_path.exists():
        LOG.error("JSON file %s not found.", json_path)
        return 1

    with json_path.open("r", encoding="utf-8") as handle:
        problems: Dict[str, Dict[str, object]] = json.load(handle)

    base_assignments = {problem_id: assign_base_milestone(record) for problem_id, record in problems.items()}

    base_assignments = detect_focus_milestones(
        problems,
        base_assignments,
        list(BASE_MILESTONES.keys()),
        threshold=args.category_threshold,
    )

    milestone_stats = apply_assignments(problems, base_assignments)

    default_owner, default_repo = parse_owner_repo(DEFAULT_OWNER, DEFAULT_REPO)
    owner = args.owner or default_owner
    repo = args.repo or default_repo
    manager = GitHubMilestoneManager(owner=owner, repo=repo, token=args.token, dry_run=args.dry_run)

    assigned_infos: Dict[str, MilestoneInfo] = {}
    resolved_titles: Dict[str, str] = {}
    for title, stats in milestone_stats.items():
        description = BASE_MILESTONES.get(title) or format_description(title, stats)
        info = manager.ensure(title=title, description=description, parent=stats.get("parent"))
        resolved_titles[title] = info.title
        assigned_infos[info.title] = info

    for record in problems.values():
        raw_title = record.get("milestone")
        if raw_title:
            resolved_title = resolved_titles.get(raw_title, manager.resolve_title(raw_title))
            record["milestone"] = resolved_title
        parent_title = record.get("milestone_parent")
        if parent_title:
            resolved_parent = resolved_titles.get(parent_title, manager.resolve_title(parent_title))
            record["milestone_parent"] = resolved_parent
        info = assigned_infos.get(record.get("milestone"))
        record["milestone_number"] = info.number if info else None
        record["milestone_url"] = info.url if info else None

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(problems, handle, indent=2)
    LOG.info("Updated %s with milestone assignments.", json_path)

    update_database(args.db, assigned_infos, problems)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
