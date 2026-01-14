"""Apply milestone assignments from issue_milestone_assignments.json to GitHub issues.

This script updates GitHub issue milestones to match the categorizations produced by
`scripts/categorize_issues_by_milestone.py`. Only milestone assignments are modified; labels are
left untouched. Run with `--dry-run` first to verify changes.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

import requests

DEFAULT_ASSIGNMENTS = Path("issue_milestone_assignments.json")
DEFAULT_OWNER = "rhamenator"
DEFAULT_REPO = "ai-scraping-defense"
REQUEST_TIMEOUT = 30
RATE_LIMIT_SLEEP = 0.25
MILESTONE_PREFIX_RE = re.compile(r"^\s*(\d+)\.\s*(.+)$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--assignments",
        type=Path,
        default=DEFAULT_ASSIGNMENTS,
        help="Path to JSON produced by categorize_issues_by_milestone.py",
    )
    parser.add_argument("--owner", type=str, default=None, help="GitHub repository owner")
    parser.add_argument("--repo", type=str, default=None, help="GitHub repository name")
    parser.add_argument("--token", type=str, default=os.environ.get("GITHUB_TOKEN"), help="GitHub token")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without applying changes")
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: INFO)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any assignment references a missing milestone (default: skip with warning).",
    )
    return parser.parse_args()


def parse_owner_repo(default_owner: str, default_repo: str) -> tuple[str, str]:
    env_repo = os.environ.get("GITHUB_REPOSITORY")
    if env_repo and "/" in env_repo:
        owner, repo = env_repo.split("/", 1)
        return owner, repo
    return default_owner, default_repo


def normalize_milestone_title(title: str) -> str:
    match = MILESTONE_PREFIX_RE.match(title)
    if match:
        return match.group(2).strip()
    return title.strip()


def build_milestone_lookups(milestones: Dict[str, dict]) -> tuple[Dict[str, int], Dict[str, list[str]]]:
    by_title = {title: details["number"] for title, details in milestones.items()}
    normalized = {}
    for title in milestones:
        normalized_title = normalize_milestone_title(title)
        normalized.setdefault(normalized_title, []).append(title)
    return by_title, normalized


@dataclass
class IssueRecord:
    number: int
    title: str
    milestone_number: Optional[int]
    milestone_title: Optional[str]


class GitHubClient:
    def __init__(self, owner: str, repo: str, token: Optional[str]) -> None:
        self.owner = owner
        self.repo = repo
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "User-Agent": "milestone-sync",
            }
        )
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def _url(self, suffix: str) -> str:
        return f"https://api.github.com/repos/{self.owner}/{self.repo}/{suffix}"

    def fetch_issues(self) -> Dict[str, IssueRecord]:
        issues_by_title: Dict[str, IssueRecord] = {}
        page = 1
        while True:
            params = {"state": "all", "per_page": 100, "page": page}
            response = self.session.get(self._url("issues"), params=params, timeout=REQUEST_TIMEOUT)
            if response.status_code == 401:
                raise RuntimeError("GitHub authentication failed when listing issues.")
            response.raise_for_status()
            payload = response.json()
            if not payload:
                break
            for issue in payload:
                if "pull_request" in issue:
                    continue
                milestone = issue.get("milestone")
                record = IssueRecord(
                    number=issue["number"],
                    title=issue["title"],
                    milestone_number=milestone.get("number") if milestone else None,
                    milestone_title=milestone.get("title") if milestone else None,
                )
                if record.title in issues_by_title:
                    logging.warning(
                        "Duplicate issue title detected ('%s'); keeping issue #%s.",
                        record.title,
                        record.number,
                    )
                issues_by_title[record.title] = record
            if "next" not in response.links:
                break
            page += 1
        logging.info("Fetched %d issues from GitHub (excluding PRs).", len(issues_by_title))
        return issues_by_title

    def fetch_milestones(self) -> Dict[str, dict]:
        milestones: Dict[str, dict] = {}
        page = 1
        while True:
            params = {"state": "all", "per_page": 100, "page": page}
            response = self.session.get(self._url("milestones"), params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            if not payload:
                break
            for milestone in payload:
                milestones[milestone["title"]] = milestone
            if "next" not in response.links:
                break
            page += 1
        logging.info("Fetched %d milestones from GitHub.", len(milestones))
        return milestones

    def update_issue_milestone(self, issue_number: int, milestone_number: int, dry_run: bool = False) -> None:
        if dry_run:
            logging.info(
                "[dry-run] Would update issue #%s milestone to #%s.",
                issue_number,
                milestone_number,
            )
            return
        payload = {"milestone": milestone_number}
        response = self.session.patch(
            self._url(f"issues/{issue_number}"),
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

    def clear_issue_milestone(self, issue_number: int, dry_run: bool = False) -> None:
        if dry_run:
            logging.info("[dry-run] Would clear milestone on issue #%s.", issue_number)
            return
        payload = {"milestone": None}
        response = self.session.patch(
            self._url(f"issues/{issue_number}"),
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()


def load_assignments(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("Assignments file must be a JSON array.")
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("Each assignment entry must be an object.")
        if "issue_id" not in entry or "milestone" not in entry:
            raise ValueError("Each assignment entry must include 'issue_id' and 'milestone'.")
        yield entry


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(message)s")

    if not args.token:
        logging.error("GITHUB_TOKEN is required for GitHub API access.")
        return 1

    if not args.assignments.exists():
        logging.error("Assignments file %s not found.", args.assignments)
        return 1

    owner_default, repo_default = parse_owner_repo(DEFAULT_OWNER, DEFAULT_REPO)
    owner = args.owner or owner_default
    repo = args.repo or repo_default
    client = GitHubClient(owner=owner, repo=repo, token=args.token)

    assignments = list(load_assignments(args.assignments))
    issues = client.fetch_issues()
    milestones = client.fetch_milestones()

    milestone_title_to_number, normalized_titles = build_milestone_lookups(milestones)

    updates = 0
    skipped_missing_milestone = 0
    skipped_missing_issue = 0
    already_matching = 0

    for entry in assignments:
        title = entry["issue_id"]
        target_milestone_title = entry["milestone"]
        issue = issues.get(title)
        if not issue:
            skipped_missing_issue += 1
            logging.warning("No GitHub issue found for '%s'; skipping.", title)
            continue

        if target_milestone_title == "Untriaged":
            target_number = None
        else:
            target_number = milestone_title_to_number.get(target_milestone_title)
            if target_number is None:
                normalized_target = normalize_milestone_title(target_milestone_title)
                candidates = normalized_titles.get(normalized_target, [])
                if len(candidates) == 1:
                    resolved = candidates[0]
                    target_number = milestone_title_to_number[resolved]
                    logging.info("Resolved milestone '%s' to '%s'.", target_milestone_title, resolved)
                elif len(candidates) > 1:
                    logging.warning(
                        "Milestone '%s' matches multiple prefixed milestones: %s",
                        target_milestone_title,
                        ", ".join(sorted(candidates)),
                    )

        if target_number is None and target_milestone_title != "Untriaged":
            skipped_missing_milestone += 1
            message = f"Milestone '{target_milestone_title}' not found for issue '{title}'."
            if args.strict:
                logging.error(message)
                return 1
            logging.warning(message)
            continue

        current_title = issue.milestone_title
        current_number = issue.milestone_number

        if target_milestone_title == current_title:
            already_matching += 1
            continue

        logging.info(
            "Updating issue #%s (%s): %s -> %s",
            issue.number,
            title,
            current_title or "None",
            target_milestone_title,
        )

        if target_milestone_title == "Untriaged":
            client.clear_issue_milestone(issue.number, dry_run=args.dry_run)
        else:
            client.update_issue_milestone(issue.number, target_number, dry_run=args.dry_run)

        updates += 1
        if not args.dry_run:
            time.sleep(RATE_LIMIT_SLEEP)

    logging.info("Processed %d assignments.", len(assignments))
    logging.info("%d updates applied, %d already matched.", updates, already_matching)
    if skipped_missing_issue:
        logging.info("%d assignments skipped due to missing issues.", skipped_missing_issue)
    if skipped_missing_milestone:
        logging.info("%d assignments skipped due to missing milestones.", skipped_missing_milestone)

    if args.dry_run:
        logging.info("Dry run mode; no GitHub issues were modified.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
