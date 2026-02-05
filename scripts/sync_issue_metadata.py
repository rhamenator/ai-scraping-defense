"""Synchronise GitHub issue labels and milestones with problem_file_map metadata.

Usage:
    python scripts/sync_issue_metadata.py [--dry-run]

The script reads `problem_file_map.json`, derives category- and severity-based
labels for each problem, guarantees that those labels exist in the repository,
and applies the labels and resolved milestone to the matching GitHub issue.

Matching is performed by exact issue title. Issues without a corresponding
problem entry are ignored. Milestone numbers produced by
`scripts/update_problem_milestones.py` are reused, so run that script first when
milestone assignments or mappings change.

Requires a GitHub token in `GITHUB_TOKEN` (PAT or gh auth token) with `repo`
scope. The repository defaults to `rhamenator/ai-scraping-defense`, but can be
overridden via the `GITHUB_REPOSITORY` environment variable or command line
flags.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import textwrap
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import requests

LOG = logging.getLogger("sync_issue_metadata")

DEFAULT_JSON = Path("problem_file_map.json")
DEFAULT_OWNER = "rhamenator"
DEFAULT_REPO = "ai-scraping-defense"
LABEL_PREFIX_CATEGORY = "category::"
LABEL_PREFIX_SEVERITY = "severity::"
REQUEST_TIMEOUT = 30
RATE_LIMIT_SLEEP = 0.25
AUTOMATION_LABEL = "automated-issue"

CATEGORY_LABEL_COLOR = "0366d6"  # GitHub blue
CATEGORY_LABEL_DESCRIPTIONS = defaultdict(
    lambda: "Automatically assigned category label from problem_file_map.json."
)
SEVERITY_LABEL_COLOR = {
    "High": "d73a4a",  # red
    "Medium": "fbca04",  # yellow
    "Low": "0e8a16",  # green
}
SEVERITY_LABEL_DESCRIPTIONS = {
    "High": "High severity issue per problem_file_map.json.",
    "Medium": "Medium severity issue per problem_file_map.json.",
    "Low": "Low severity issue per problem_file_map.json.",
}
AUTOMATION_LABEL_COLOR = "6f42c1"
AUTOMATION_LABEL_DESCRIPTION = "Issue generated from problem_file_map automation."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", type=Path, default=DEFAULT_JSON, help="Path to problem_file_map.json"
    )
    parser.add_argument(
        "--owner", type=str, default=None, help="GitHub repository owner"
    )
    parser.add_argument("--repo", type=str, default=None, help="GitHub repository name")
    parser.add_argument(
        "--token", type=str, default=os.environ.get("GITHUB_TOKEN"), help="GitHub token"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Log actions without applying changes"
    )
    parser.add_argument(
        "--create-missing",
        action="store_true",
        help="Create GitHub issues for problem entries without a matching issue.",
    )
    parser.add_argument(
        "--log-level", default="INFO", help="Logging level (default: INFO)"
    )
    return parser.parse_args()


@dataclass
class IssueRecord:
    number: int
    title: str
    labels: Set[str]
    milestone_number: Optional[int]


class GitHubClient:
    def __init__(self, owner: str, repo: str, token: Optional[str]) -> None:
        self.owner = owner
        self.repo = repo
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "User-Agent": "problem-map-sync",
            }
        )
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        self._label_cache: Dict[str, dict] = {}

    # -----------------------------------------------------------
    def _url(self, suffix: str) -> str:
        return f"https://api.github.com/repos/{self.owner}/{self.repo}/{suffix}"

    # -----------------------------------------------------------
    def fetch_issues(self) -> Dict[str, IssueRecord]:
        issues_by_title: Dict[str, IssueRecord] = {}
        page = 1
        while True:
            params = {"state": "all", "per_page": 100, "page": page}
            response = self.session.get(
                self._url("issues"), params=params, timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 401:
                raise RuntimeError("GitHub authentication failed when listing issues.")
            response.raise_for_status()
            payload = response.json()
            if not payload:
                break
            for issue in payload:
                if "pull_request" in issue:
                    continue  # skip PRs
                title = issue["title"]
                record = IssueRecord(
                    number=issue["number"],
                    title=title,
                    labels={label["name"] for label in issue.get("labels", [])},
                    milestone_number=(
                        issue.get("milestone", {}).get("number")
                        if issue.get("milestone")
                        else None
                    ),
                )
                if title in issues_by_title:
                    LOG.warning(
                        "Duplicate issue title detected ('%s'); keeping the most recently fetched issue #%s.",
                        title,
                        record.number,
                    )
                issues_by_title[title] = record
            if "next" not in response.links:
                break
            page += 1
        LOG.info("Fetched %d issues from GitHub (excluding PRs).", len(issues_by_title))
        return issues_by_title

    # -----------------------------------------------------------
    def fetch_labels(self) -> Dict[str, dict]:
        if self._label_cache:
            return self._label_cache
        page = 1
        labels: Dict[str, dict] = {}
        while True:
            params = {"per_page": 100, "page": page}
            response = self.session.get(
                self._url("labels"), params=params, timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            payload = response.json()
            if not payload:
                break
            for label in payload:
                labels[label["name"]] = label
            if "next" not in response.links:
                break
            page += 1
        self._label_cache = labels
        LOG.info("Fetched %d existing labels from GitHub.", len(labels))
        return labels

    # -----------------------------------------------------------
    def ensure_label(
        self, name: str, color: str, description: Optional[str], dry_run: bool = False
    ) -> None:
        labels = self.fetch_labels()
        if name in labels:
            return
        if dry_run:
            LOG.info("[dry-run] Would create label '%s'.", name)
            return
        payload = {"name": name, "color": color, "description": description or ""}
        response = self.session.post(
            self._url("labels"), json=payload, timeout=REQUEST_TIMEOUT
        )
        if response.status_code == 422:
            # Label already exists (race). Refresh cache and move on.
            self._label_cache = {}
            self.fetch_labels()
            return
        response.raise_for_status()
        # Update cache entries
        if not self._label_cache:
            self._label_cache = {}
        self._label_cache[name] = response.json()
        LOG.info("Created label '%s'.", name)

    # -----------------------------------------------------------
    def update_issue(
        self, issue_number: int, labels: Iterable[str], milestone: Optional[int]
    ) -> None:
        payload = {"labels": sorted(labels)}
        if milestone is not None:
            payload["milestone"] = milestone
        response = self.session.patch(
            self._url(f"issues/{issue_number}"), json=payload, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()

    # -----------------------------------------------------------
    def create_issue(
        self,
        title: str,
        body: str,
        labels: Iterable[str],
        milestone: Optional[int],
        dry_run: bool = False,
    ) -> Optional[IssueRecord]:
        if dry_run:
            LOG.info(
                "[dry-run] Would create issue '%s' with labels %s and milestone %s.",
                title,
                sorted(labels),
                milestone,
            )
            return None

        payload = {
            "title": title,
            "body": body,
            "labels": sorted(labels),
        }
        if milestone is not None:
            payload["milestone"] = milestone

        response = self.session.post(
            self._url("issues"), json=payload, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        LOG.info("Created issue #%s for '%s'.", data["number"], title)
        return IssueRecord(
            number=data["number"],
            title=data["title"],
            labels=set(labels),
            milestone_number=milestone,
        )


def parse_owner_repo(default_owner: str, default_repo: str) -> Tuple[str, str]:
    env_repo = os.environ.get("GITHUB_REPOSITORY")
    if env_repo and "/" in env_repo:
        owner, repo = env_repo.split("/", 1)
        return owner, repo
    return default_owner, default_repo


def build_issue_body(title: str, record: Dict[str, object]) -> str:
    category = record.get("category") or "Unspecified"
    severity = record.get("severity") or "Unspecified"
    confidence = record.get("confidence")
    milestone_focus = record.get("milestone_parent") or record.get("milestone")
    fix_prompt = (record.get("fix_prompt") or "").strip()
    original_affected = record.get("original_affected") or []
    resolved_files = record.get("resolved_files") or []

    header_lines = [f"**Category**: {category}", f"**Severity**: {severity}"]
    if confidence is not None:
        header_lines.append(f"**Confidence**: {confidence}")
    if milestone_focus:
        header_lines.append(f"**Focus Area**: {milestone_focus}")

    sections: List[str] = ["\n".join(header_lines)]

    if fix_prompt:
        sections.append("## Recommended Fix\n" + fix_prompt)

    if original_affected:
        affected_block = "\n".join(f"- {item}" for item in original_affected)
        sections.append("## Initially Affected\n" + affected_block)

    if resolved_files:
        resolved_block = "\n".join(f"- {item}" for item in resolved_files)
        sections.append("## Target Files\n" + resolved_block)

    return textwrap.dedent("\n\n".join(sections)).strip()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(message)s",
    )

    if not args.token:
        LOG.error("GITHUB_TOKEN is required for GitHub API access.")
        return 1

    json_path = args.json
    if not json_path.exists():
        LOG.error("Problem map JSON %s not found.", json_path)
        return 1

    with json_path.open("r", encoding="utf-8") as handle:
        problems: Dict[str, Dict[str, object]] = json.load(handle)

    owner_default, repo_default = parse_owner_repo(DEFAULT_OWNER, DEFAULT_REPO)
    owner = args.owner or owner_default
    repo = args.repo or repo_default
    client = GitHubClient(owner=owner, repo=repo, token=args.token)

    issue_map = client.fetch_issues()
    client.fetch_labels()

    updates = 0
    missing_issues = 0

    for title, record in problems.items():
        issue = issue_map.get(title)
        category = str(record.get("category", "")).strip()
        severity = str(record.get("severity", "")).strip()
        milestone_number = record.get("milestone_number")
        if milestone_number is not None:
            try:
                milestone_number = int(milestone_number)
            except (TypeError, ValueError):
                LOG.warning(
                    "Milestone number for '%s' is not an integer: %s",
                    title,
                    milestone_number,
                )
                milestone_number = None

        desired_labels = set(issue.labels) if issue else set()
        if category:
            category_label = f"{LABEL_PREFIX_CATEGORY}{category}"
            client.ensure_label(
                category_label,
                CATEGORY_LABEL_COLOR,
                CATEGORY_LABEL_DESCRIPTIONS[category],
                dry_run=args.dry_run,
            )
            desired_labels.add(category_label)
        if severity:
            severity_label = f"{LABEL_PREFIX_SEVERITY}{severity}"
            color = SEVERITY_LABEL_COLOR.get(severity, "bdbdbd")
            description = SEVERITY_LABEL_DESCRIPTIONS.get(
                severity, "Severity label assigned from problem map."
            )
            client.ensure_label(
                severity_label, color, description, dry_run=args.dry_run
            )
            desired_labels.add(severity_label)

        if not issue:
            desired_labels.add(AUTOMATION_LABEL)
            client.ensure_label(
                AUTOMATION_LABEL,
                AUTOMATION_LABEL_COLOR,
                AUTOMATION_LABEL_DESCRIPTION,
                dry_run=args.dry_run,
            )

            if not args.create_missing:
                missing_issues += 1
                LOG.debug("No GitHub issue found for '%s'; skipping.", title)
                continue

            body = build_issue_body(title, record)
            LOG.info("Creating issue for '%s'.", title)
            created = client.create_issue(
                title, body, desired_labels, milestone_number, dry_run=args.dry_run
            )
            if created is None:
                missing_issues += 1
                continue

            issue_map[title] = created
            updates += 1
            if not args.dry_run:
                time.sleep(RATE_LIMIT_SLEEP)
            continue

        if (
            desired_labels == issue.labels
            and milestone_number == issue.milestone_number
        ):
            continue

        updates += 1
        LOG.info(
            "Updating issue #%s (%s): labels -> %s, milestone -> %s",
            issue.number,
            title,
            sorted(desired_labels),
            milestone_number,
        )

        if args.dry_run:
            continue

        try:
            client.update_issue(issue.number, desired_labels, milestone_number)
            # Update local cache for subsequent logic
            issue.labels = desired_labels
            issue.milestone_number = milestone_number
            time.sleep(RATE_LIMIT_SLEEP)
        except requests.HTTPError as exc:
            LOG.error("Failed to update issue #%s: %s", issue.number, exc)

    LOG.info(
        "Processed %d problems; %d issues updated, %d without matching GitHub issues.",
        len(problems),
        updates,
        missing_issues,
    )
    if args.dry_run:
        LOG.info("Dry run mode; no GitHub issues were modified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
