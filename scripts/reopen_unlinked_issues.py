#!/usr/bin/env python3
"""
Reopen issues that don't have an associated merged PR.

This script identifies closed issues that lack a merged pull request
and reopens them to ensure issues are not prematurely closed.

Usage:
    python scripts/reopen_unlinked_issues.py [--dry-run] [--limit N]

Requires:
    - GitHub CLI (gh) authenticated
    - GITHUB_TOKEN environment variable with repo scope
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time

LOG = logging.getLogger("reopen_unlinked_issues")

DEFAULT_LIMIT = 500
RATE_LIMIT_SLEEP = 0.5

# Regex pattern for extracting issue numbers from text
# Matches # followed by digits, but only when:
# - Not preceded by alphanumeric or underscore (avoids hex in commit SHAs)
# - Followed by word boundary (avoids matching middle of longer numbers)
ISSUE_REFERENCE_PATTERN = re.compile(r"(?<![a-zA-Z0-9_])#(\d+)\b")


def run_gh_command(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a GitHub CLI command and return the result."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check,
            env={**os.environ, "GH_PAGER": ""},
        )
        return result
    except subprocess.CalledProcessError as e:
        LOG.error(f"GitHub CLI command failed: {' '.join(cmd)}")
        LOG.error(f"Error: {e.stderr}")
        raise


def fetch_closed_issues(limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Fetch closed issues from GitHub."""
    LOG.info(f"Fetching up to {limit} closed issues from GitHub...")
    cmd = [
        "gh",
        "issue",
        "list",
        "--state",
        "closed",
        "--json",
        "number,title,closedAt,stateReason",
        "--limit",
        str(limit),
    ]
    result = run_gh_command(cmd)
    issues = json.loads(result.stdout)
    LOG.info(f"Fetched {len(issues)} closed issues.")
    return issues


def fetch_pull_requests(state: str = "all", limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Fetch pull requests from GitHub."""
    LOG.info(f"Fetching pull requests with state={state} (limit={limit})...")
    cmd = [
        "gh",
        "pr",
        "list",
        "--state",
        state,
        "--json",
        "number,title,body,merged,mergedAt,closingIssuesReferences",
        "--limit",
        str(limit),
    ]
    result = run_gh_command(cmd)
    prs = json.loads(result.stdout)
    LOG.info(f"Fetched {len(prs)} pull requests.")
    return prs


def extract_issue_numbers_from_text(text: str) -> set[int]:
    """
    Extract issue numbers from text using common patterns.

    Patterns recognized:
    - Fixes #123
    - Closes #123
    - Resolves #123
    - Fix #123
    - Close #123
    - Resolve #123
    - #123 (standalone with word boundaries to avoid commit SHAs)
    """
    if not text:
        return set()

    issue_numbers = set()
    text_lower = text.lower()

    matches = ISSUE_REFERENCE_PATTERN.finditer(text_lower)
    for match in matches:
        try:
            issue_numbers.add(int(match.group(1)))
        except (ValueError, IndexError):
            continue

    return issue_numbers


def build_pr_to_issues_map(prs: list[dict]) -> dict[int, set[int]]:
    """
    Build a mapping of PR numbers to the issues they reference.

    Returns:
        dict mapping PR number to set of issue numbers it closes/references.
    """
    pr_to_issues = {}

    for pr in prs:
        pr_number = pr.get("number")
        if not pr_number:
            continue

        referenced_issues = set()

        # Check closingIssuesReferences (GitHub's native linking)
        closing_refs = pr.get("closingIssuesReferences", {})
        if isinstance(closing_refs, dict) and "nodes" in closing_refs:
            for node in closing_refs.get("nodes", []):
                if isinstance(node, dict) and "number" in node:
                    referenced_issues.add(node["number"])

        # Also check body text for manual references
        body = pr.get("body", "") or ""
        title = pr.get("title", "") or ""
        referenced_issues.update(extract_issue_numbers_from_text(body))
        referenced_issues.update(extract_issue_numbers_from_text(title))

        if referenced_issues:
            pr_to_issues[pr_number] = referenced_issues
            LOG.debug(f"PR #{pr_number} references issues: {referenced_issues}")

    return pr_to_issues


def build_issue_to_prs_map(
    pr_to_issues: dict[int, set[int]], prs: list[dict]
) -> dict[int, list[dict]]:
    """
    Build a reverse mapping of issue numbers to the PRs that reference them.

    Returns:
        dict mapping issue number to list of PRs (with merged status).
    """
    issue_to_prs = {}
    pr_details = {pr["number"]: pr for pr in prs}

    for pr_number, issue_numbers in pr_to_issues.items():
        pr = pr_details.get(pr_number)
        if not pr:
            continue

        for issue_number in issue_numbers:
            if issue_number not in issue_to_prs:
                issue_to_prs[issue_number] = []
            issue_to_prs[issue_number].append(
                {
                    "number": pr_number,
                    "merged": pr.get("merged", False),
                    "mergedAt": pr.get("mergedAt"),
                    "title": pr.get("title", ""),
                }
            )

    return issue_to_prs


def has_merged_pr(issue_number: int, issue_to_prs: dict[int, list[dict]]) -> bool:
    """Check if an issue has at least one merged PR."""
    prs = issue_to_prs.get(issue_number, [])
    return any(pr.get("merged", False) for pr in prs)


def reopen_issue(issue_number: int, reason: str, dry_run: bool = False) -> bool:
    """
    Reopen a GitHub issue.

    Args:
        issue_number: The issue number to reopen.
        reason: Comment to add when reopening.
        dry_run: If True, only log the action without executing.

    Returns:
        True if successful, False otherwise.
    """
    if dry_run:
        LOG.info(f"[DRY-RUN] Would reopen issue #{issue_number}: {reason}")
        return True

    try:
        # Reopen the issue
        LOG.info(f"Reopening issue #{issue_number}...")
        cmd = ["gh", "issue", "reopen", str(issue_number)]
        run_gh_command(cmd)

        # Add a comment explaining why
        comment = f"Reopening this issue as it was closed without an associated merged PR.\n\n{reason}"
        cmd = ["gh", "issue", "comment", str(issue_number), "--body", comment]
        run_gh_command(cmd)

        LOG.info(f"Successfully reopened issue #{issue_number}")
        return True
    except subprocess.CalledProcessError as e:
        LOG.error(f"Failed to reopen issue #{issue_number}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log actions without making changes to GitHub",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Maximum number of issues/PRs to fetch (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s: %(message)s",
    )

    # Check for GitHub CLI
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        LOG.error("GitHub CLI (gh) is not installed or not in PATH")
        LOG.error("Install from: https://cli.github.com/")
        return 1

    # Fetch data
    closed_issues = fetch_closed_issues(limit=args.limit)
    if not closed_issues:
        LOG.info("No closed issues found.")
        return 0

    # Fetch PRs (merged and closed to find linked issues)
    all_prs = fetch_pull_requests(state="all", limit=args.limit)

    # Build mappings
    LOG.info("Building PR-to-issue mappings...")
    pr_to_issues = build_pr_to_issues_map(all_prs)
    issue_to_prs = build_issue_to_prs_map(pr_to_issues, all_prs)

    # Identify issues to reopen
    issues_to_reopen = []
    for issue in closed_issues:
        issue_number = issue.get("number")
        if not issue_number:
            continue

        # Check if issue has a merged PR
        if has_merged_pr(issue_number, issue_to_prs):
            LOG.debug(f"Issue #{issue_number} has a merged PR, skipping.")
            continue

        # Check if it has any PR references (even if not merged)
        prs = issue_to_prs.get(issue_number, [])
        if prs:
            pr_list = ", ".join(f"#{pr['number']}" for pr in prs)
            reason = f"Associated PRs ({pr_list}) exist but none are merged."
            LOG.info(f"Issue #{issue_number}: {reason}")
        else:
            reason = "No associated pull requests found."
            LOG.info(f"Issue #{issue_number}: {reason}")

        issues_to_reopen.append(
            {
                "number": issue_number,
                "title": issue.get("title", ""),
                "reason": reason,
            }
        )

    # Reopen issues
    if not issues_to_reopen:
        LOG.info("No issues need to be reopened.")
        return 0

    LOG.info(f"Found {len(issues_to_reopen)} issues to reopen.")

    success_count = 0
    for issue_info in issues_to_reopen:
        if reopen_issue(
            issue_info["number"], issue_info["reason"], dry_run=args.dry_run
        ):
            success_count += 1

        if not args.dry_run:
            time.sleep(RATE_LIMIT_SLEEP)

    LOG.info(f"Reopened {success_count} of {len(issues_to_reopen)} issues.")

    if args.dry_run:
        LOG.info("Dry run mode - no changes were made to GitHub.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
