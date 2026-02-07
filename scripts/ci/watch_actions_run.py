#!/usr/bin/env python3
"""
Watch GitHub Actions run progress from a local terminal.

This is intended as a lightweight progress indicator for long-running CI checks.
It uses the authenticated `gh` CLI for API access (no extra secrets required).

Examples:
  # Watch a specific run id
  python scripts/ci/watch_actions_run.py --run-id 1234567890

  # Watch the latest run for a workflow on main
  python scripts/ci/watch_actions_run.py --workflow security-controls.yml --branch main
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional


def _require_gh() -> None:
    if shutil.which("gh") is None:
        raise SystemExit(
            "Missing `gh` (GitHub CLI). Install it and authenticate with `gh auth login`."
        )


def _run_gh_json(args: list[str]) -> Any:
    completed = subprocess.run(
        ["gh", *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.stderr.strip() or "gh command failed")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Failed to parse gh output as JSON: {exc}") from exc


def _repo_slug() -> str:
    out = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if out.returncode != 0:
        raise SystemExit(out.stderr.strip() or "Unable to determine repository slug")
    slug = out.stdout.strip()
    if not slug or "/" not in slug:
        raise SystemExit(f"Unexpected repo slug: {slug!r}")
    return slug


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    # GitHub uses RFC3339/ISO with Z
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _fmt_age(started_at: Optional[str]) -> str:
    started = _parse_iso(started_at)
    if not started:
        return "?"
    delta = datetime.now(timezone.utc) - started.astimezone(timezone.utc)
    seconds = int(delta.total_seconds())
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m{seconds:02d}s"


@dataclass(frozen=True)
class JobProgress:
    name: str
    status: str
    conclusion: Optional[str]
    current_step: Optional[str]


def _job_progress(job: dict[str, Any]) -> JobProgress:
    steps: list[dict[str, Any]] = job.get("steps") or []
    current_step = None
    for step in steps:
        if step.get("status") == "in_progress":
            current_step = step.get("name")
            break
    if current_step is None and steps:
        last = steps[-1]
        current_step = last.get("name")
    return JobProgress(
        name=job.get("name", "<unnamed>"),
        status=job.get("status", "unknown"),
        conclusion=job.get("conclusion"),
        current_step=current_step,
    )


def _latest_run_id(repo: str, workflow: str, branch: str) -> int:
    runs = _run_gh_json(
        [
            "api",
            f"/repos/{repo}/actions/workflows/{workflow}/runs",
            "-f",
            f"branch={branch}",
            "-f",
            "per_page=1",
        ]
    )
    workflow_runs = runs.get("workflow_runs") or []
    if not workflow_runs:
        raise SystemExit(f"No runs found for workflow={workflow!r} branch={branch!r}")
    return int(workflow_runs[0]["id"])


def _fetch_run(repo: str, run_id: int) -> dict[str, Any]:
    return _run_gh_json(["api", f"/repos/{repo}/actions/runs/{run_id}"])


def _fetch_jobs(repo: str, run_id: int) -> list[dict[str, Any]]:
    jobs_resp = _run_gh_json(
        ["api", f"/repos/{repo}/actions/runs/{run_id}/jobs", "-f", "per_page=100"]
    )
    return jobs_resp.get("jobs") or []


def _print_status(
    *,
    run: dict[str, Any],
    jobs: list[dict[str, Any]],
    show_jobs: bool,
) -> None:
    total = len(jobs)
    completed = sum(1 for j in jobs if j.get("status") == "completed")
    running = [j for j in jobs if j.get("status") == "in_progress"]

    run_name = run.get("name") or "<unnamed>"
    status = run.get("status") or "unknown"
    conclusion = run.get("conclusion") or ""
    head_branch = run.get("head_branch") or ""

    parts = [
        f"{run_name} [{head_branch}]",
        f"status={status}{'/' + conclusion if conclusion else ''}",
        f"jobs={completed}/{total}",
        f"age={_fmt_age(run.get('run_started_at'))}",
    ]
    print(" | ".join(parts))

    if show_jobs and running:
        for job in running:
            jp = _job_progress(job)
            step = f" :: {jp.current_step}" if jp.current_step else ""
            print(f"  - {jp.name}{step}")


def _iter_until_done(repo: str, run_id: int, interval: float, show_jobs: bool) -> int:
    while True:
        run = _fetch_run(repo, run_id)
        jobs = _fetch_jobs(repo, run_id)

        # Clear-ish output (portable)
        print("\n" + ("=" * 80))
        _print_status(run=run, jobs=jobs, show_jobs=show_jobs)

        if run.get("status") == "completed":
            conclusion = run.get("conclusion") or "unknown"
            print(f"Completed: {conclusion}")
            return 0 if conclusion == "success" else 1

        time.sleep(interval)


def main(argv: Optional[Iterable[str]] = None) -> int:
    _require_gh()
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-id", type=int, help="GitHub Actions run id to watch")
    group.add_argument(
        "--workflow",
        help="Workflow file name (e.g., security-controls.yml) to watch latest run",
    )
    parser.add_argument("--branch", default="main", help="Branch for --workflow mode")
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="Refresh interval in seconds (default: 10)",
    )
    parser.add_argument(
        "--show-jobs",
        action="store_true",
        help="Print currently running job(s) and step name(s)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    repo = _repo_slug()
    run_id = args.run_id or _latest_run_id(repo, args.workflow, args.branch)
    print(f"Watching run {run_id} in {repo}...")
    return _iter_until_done(repo, run_id, args.interval, args.show_jobs)


if __name__ == "__main__":
    raise SystemExit(main())
