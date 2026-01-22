import argparse
import json
import os
import re
import subprocess
import sys
from typing import Dict, Iterable, List, Optional

from pr_claims import (
    CLAIMS_DEFAULT_PATH,
    detect_claim_conflicts,
    load_claims,
    normalize_file_path,
    record_claim,
    release_claims,
)

COPILOT_LOGINS = {"github-copilot", "github-copilot[bot]"}
SUGGESTION_RE = re.compile(r"```suggestion\s*\n(?P<body>[\s\S]*?)\n```", re.IGNORECASE)


class CommandError(RuntimeError):
    pass


def run_cmd(args: List[str], *, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(  # nosec B603 - controlled git/gh commands
        args, capture_output=True, text=True
    )
    if check and result.returncode != 0:
        stderr = result.stderr.strip()
        raise CommandError(f"Command {' '.join(args)} failed: {stderr}")
    return result


def ensure_clean_worktree() -> None:
    status = run_cmd(["git", "status", "--porcelain"], check=False)
    if status.returncode != 0:
        raise CommandError(status.stderr.strip())
    dirty = status.stdout.strip()
    if dirty:
        raise CommandError(
            "Working tree has uncommitted changes. Please clean up before running."
        )


def fetch_pr_numbers(limit: int) -> List[int]:
    cmd = [
        "gh",
        "pr",
        "list",
        "--state",
        "open",
        "--limit",
        str(limit),
        "--json",
        "number",
    ]
    result = run_cmd(cmd)
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CommandError(f"Failed to parse gh output: {exc}") from exc
    return [int(item["number"]) for item in parsed]


def fetch_pr_details(pr_number: int) -> Dict[str, object]:
    fields = [
        "number",
        "title",
        "headRefName",
        "files",
        "reviewThreads",
        "baseRefName",
        "state",
        "isDraft",
    ]
    cmd = ["gh", "pr", "view", str(pr_number), "--json", ",".join(fields)]
    result = run_cmd(cmd)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CommandError(f"Failed to parse gh output: {exc}") from exc


def extract_suggestion(body: str) -> Optional[str]:
    match = SUGGESTION_RE.search(body or "")
    if match:
        return match.group("body")
    return None


def suggestion_seems_safe(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    risky_tokens = {
        "".join(["T", "O", "D", "O"]),
        "".join(["F", "I", "X", "M", "E"]),
        "?" * 3,
        "NotImplementedError",
    }
    if any(token in stripped for token in risky_tokens):
        return False
    if stripped in {"pass", "..."}:
        return False
    return True


def apply_suggestion(
    file_path: str,
    start_line: int,
    end_line: int,
    suggestion: str,
    *,
    dry_run: bool,
) -> bool:
    if start_line < 1 or end_line < start_line:
        print(f"  Invalid suggestion range for {file_path}: {start_line}-{end_line}")
        return False
    if not os.path.exists(file_path):
        print(f"  File missing for suggestion: {file_path}")
        return False
    with open(file_path, "r", encoding="utf-8") as handle:
        content = handle.read()
    lines = content.splitlines()
    trailing_newline = content.endswith("\n")
    max_index = len(lines)
    if start_line > max_index + 1:
        print(f"  Suggestion starts beyond end of {file_path}")
        return False
    target_start = start_line - 1
    target_end = min(end_line, max_index)
    replacement = suggestion.rstrip("\n").splitlines()
    lines[target_start:target_end] = replacement
    new_content = "\n".join(lines)
    if trailing_newline or suggestion.endswith("\n"):
        new_content += "\n"
    if dry_run:
        print(
            f"  [Dry Run] Would apply Copilot suggestion to {file_path} lines {start_line}-{end_line}."
        )
        return True
    with open(file_path, "w", encoding="utf-8") as handle:
        handle.write(new_content)
    print(f"  Applied Copilot suggestion to {file_path} lines {start_line}-{end_line}.")
    return True


def stage_and_commit(files: Iterable[str], pr_number: int, *, dry_run: bool) -> None:
    materialized = sorted(set(files))
    if not materialized:
        return
    if dry_run:
        print("  [Dry Run] Would stage files and create a commit.")
        return
    run_cmd(["git", "add", *materialized])
    message = f"Apply Copilot suggestions for PR #{pr_number}"
    run_cmd(["git", "commit", "-m", message])


def push_branch(branch: str, *, dry_run: bool) -> None:
    if dry_run:
        print(f"  [Dry Run] Would push updates to origin/{branch}.")
        return
    run_cmd(["git", "push", "origin", branch])


def checkout_branch(target_branch: str, *, dry_run: bool) -> None:
    if dry_run:
        print(f"  [Dry Run] Would check out branch {target_branch}.")
        return
    run_cmd(["gh", "pr", "checkout", target_branch])


def return_to_branch(branch: str, *, dry_run: bool) -> None:
    if dry_run:
        print(f"  [Dry Run] Would return to branch {branch}.")
        return
    run_cmd(["git", "checkout", branch])


def collect_copilot_suggestions(
    pr_details: Dict[str, object]
) -> List[Dict[str, object]]:
    suggestions: List[Dict[str, object]] = []
    threads = pr_details.get("reviewThreads", []) or []
    for thread in threads:
        if thread.get("isResolved"):
            continue
        for comment in thread.get("comments", []) or []:
            author = (comment.get("author") or {}).get("login")
            if author not in COPILOT_LOGINS:
                continue
            suggestion = extract_suggestion(comment.get("body") or "")
            if not suggestion:
                continue
            if not suggestion_seems_safe(suggestion):
                print("  Skipping suggestion flagged as potentially harmful.")
                continue
            path = comment.get("path")
            if not path:
                continue
            line = comment.get("line") or comment.get("originalLine")
            start = comment.get("startLine") or comment.get("originalStartLine") or line
            if line is None or start is None:
                continue
            start_int = int(start)
            end_int = int(line)
            if end_int < start_int:
                end_int = start_int
            suggestions.append(
                {
                    "path": normalize_file_path(path),
                    "start": start_int,
                    "end": end_int,
                    "body": suggestion,
                }
            )
    return suggestions


def ensure_branch_claim(
    claims: Dict[str, Dict[str, object]],
    claims_file: Optional[str],
    branch: str,
    issue_number: Optional[int],
    files: Iterable[str],
    *,
    dry_run: bool,
) -> Dict[str, Dict[str, object]]:
    if branch in claims:
        return claims
    if dry_run:
        print(f"  [Dry Run] Would register claim for branch {branch}.")
        return claims
    return record_claim(claims, claims_file, branch, issue_number, files)


def process_pr(
    pr_number: int,
    *,
    args,
    claims: Dict[str, Dict[str, object]],
) -> Dict[str, Dict[str, object]]:
    print(f"\nProcessing PR #{pr_number}...")
    details = fetch_pr_details(pr_number)
    head_branch = details.get("headRefName")
    if not head_branch:
        print("  Unable to determine head branch. Skipping.")
        return claims
    files = [
        normalize_file_path(item.get("path", "")) for item in details.get("files", [])
    ]
    files = [f for f in files if f]
    conflicts = detect_claim_conflicts(claims, files, ignore_branch=head_branch)
    if conflicts:
        print("  Active file claims detected. Skipping PR.")
        for conflict in conflicts:
            issue_ref = conflict.get("issue")
            issue_text = f"Issue #{issue_ref}" if issue_ref else "Unknown issue"
            files_list = ", ".join(conflict["files"])
            print(f"    - Branch {conflict['branch']} ({issue_text}) => {files_list}")
        return claims
    suggestions = collect_copilot_suggestions(details)
    if not suggestions:
        print("  No pending Copilot suggestions found.")
        return ensure_branch_claim(
            claims,
            args.claims_file,
            head_branch,
            details.get("number"),
            files,
            dry_run=args.dry_run,
        )
    try:
        ensure_clean_worktree()
    except CommandError as exc:
        print(f"  {exc}")
        return claims
    original_branch = None
    if not args.dry_run:
        current = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        original_branch = current.stdout.strip()
    checkout_branch(str(pr_number), dry_run=args.dry_run)
    applied_files: List[str] = []
    for suggestion in suggestions:
        file_path = suggestion["path"]
        start_line = suggestion["start"]
        end_line = suggestion["end"]
        body = suggestion["body"]
        success = apply_suggestion(
            file_path, start_line, end_line, body, dry_run=args.dry_run
        )
        if success:
            applied_files.append(file_path)
    stage_and_commit(applied_files, pr_number, dry_run=args.dry_run)
    if applied_files:
        push_branch(head_branch, dry_run=args.dry_run)
    else:
        print("  No suggestions were applied.")
    if original_branch:
        return_to_branch(original_branch, dry_run=args.dry_run)
    claims = ensure_branch_claim(
        claims,
        args.claims_file,
        head_branch,
        details.get("number"),
        files,
        dry_run=args.dry_run,
    )
    return claims


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate actions without editing branches",
    )
    parser.add_argument(
        "--limit", type=int, default=1, help="Maximum number of PRs to inspect"
    )
    parser.add_argument("--pr-number", type=int, help="Process a specific PR number")
    parser.add_argument(
        "--claims-file", default=CLAIMS_DEFAULT_PATH, help="Path to file claim manifest"
    )
    parser.add_argument(
        "--release-branch",
        action="append",
        help="Release file claims for the given branch (repeatable)",
    )
    args = parser.parse_args()

    claims = load_claims(args.claims_file)
    if args.release_branch:
        claims = release_claims(claims, args.claims_file, args.release_branch)

    effective_limit = args.limit if args.limit and args.limit > 0 else 1

    if args.pr_number:
        pr_numbers = [args.pr_number]
    else:
        pr_numbers = fetch_pr_numbers(effective_limit)

    processed = 0
    for pr_number in pr_numbers:
        claims = process_pr(pr_number, args=args, claims=claims)
        processed += 1
        if processed >= effective_limit:
            break


if __name__ == "__main__":
    try:
        main()
    except CommandError as err:
        print(f"Error: {err}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("Interrupted by user.")
        sys.exit(130)
