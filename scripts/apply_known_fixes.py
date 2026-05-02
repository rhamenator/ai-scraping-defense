"""
CLI tool to discover and process known fix JSON files across categories
(security, architecture, operations, performance, code_quality, compliance),
send each fix prompt to OpenAI using your ChatGPT account (OPENAI_API_KEY), and
optionally apply returned unified diff patches to the repository.

File discovery per category uses the pattern:
  {category}_problems + (".json" for batch 1, or "_batch{x}.json" for x > 1)

For robustness, if "{category}_problems.json" is missing, the tool will also
look for "{category}_problems_batch1.json". It then continues with
"{category}_problems_batch2.json", "{category}_problems_batch3.json", ... as
long as such files exist.

Usage examples:
  - Dry run for all discovered categories and batches:
      python scripts/apply_known_fixes.py

  - Only specific categories:
      python scripts/apply_known_fixes.py --categories security performance

  - Only specific problem IDs within each JSON (e.g., id 1 and 2):
      python scripts/apply_known_fixes.py --ids 1 2

  - Apply patches returned by the model and run pre-commit when available:
      python scripts/apply_known_fixes.py --apply

Environment:
  - OPENAI_API_KEY: Your API key (required to contact the OpenAI API)
  - OPENAI_MODEL  : Optional, default 'gpt-4o-mini'

Notes:
  - The tool extracts code context from affected_files when a real file path is
    provided (optionally with line ranges like path:12-34). Non-file notes are
    included as plain text.
  - Patches are saved per problem under --out-dir/<category>/<json_stem>.
    With --apply, the tool tries `git apply`. If pre-commit is installed, it
    runs on the changed files.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# -------- Utilities --------


def eprint(*args: object, **kwargs: object) -> None:
    print(*args, file=sys.stderr, **kwargs)


def read_text_safe(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None


def parse_range(spec: str) -> Optional[Tuple[int, int]]:
    """Parse a line range like '12-34' -> (12, 34). 1-based inclusive.
    Returns None if spec is invalid.
    """
    m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", spec)
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    if a <= 0 or b <= 0 or a > b:
        return None
    return a, b


def extract_snippet(text: str, start: int, end: int) -> str:
    """Extract 1-based inclusive line range from text safely."""
    lines = text.splitlines()
    # Clamp to available lines
    start = max(1, min(start, len(lines) if lines else 1))
    end = max(1, min(end, len(lines) if lines else 1))
    if end < start:
        start, end = end, start
    # Convert to 0-based slice
    start_index = start - 1
    return "\n".join(lines[start_index:end])


@dataclass
class AffectedContext:
    ref: str  # original ref string
    path: Optional[Path]  # None if not a resolvable path in repo
    snippet: Optional[str]  # extracted code snippet (None if not found)
    note: Optional[str]  # plain note when not a file path


def resolve_affected_item(item: str, repo_root: Path) -> AffectedContext:
    """Try to resolve an affected_files entry.

    Accepts formats like:
      - 'relative/path.py' -> entire file content as snippet
      - 'relative/path.py:12-34' -> only that line range
    If not a file (e.g., 'API endpoints throughout'), returns as note.
    """
    # Split on the first ':' to detect a potential range
    path_part: str
    range_part: Optional[str]
    if ":" in item and not item.strip().startswith("http"):
        path_part, range_part = item.split(":", 1)
    else:
        path_part, range_part = item, None

    candidate = repo_root / path_part
    if candidate.is_file():
        content = read_text_safe(candidate)
        if content is None:
            return AffectedContext(ref=item, path=candidate, snippet=None, note=None)
        if range_part:
            rng = parse_range(range_part)
            if rng:
                snippet = extract_snippet(content, *rng)
            else:
                snippet = content
        else:
            snippet = content
        return AffectedContext(ref=item, path=candidate, snippet=snippet, note=None)

    # Not a resolvable file path; treat as a note.
    return AffectedContext(ref=item, path=None, snippet=None, note=item)


# -------- OpenAI interaction --------


def build_system_prompt() -> str:
    return (
        "You are a senior security engineer working in a monorepo. "
        "You receive a security problem description and related code context. "
        "Produce a minimal, high-confidence fix as a single unified diff patch that can be applied from the repo root. "
        "Follow these rules: "
        "1) Output ONLY one fenced code block containing the patch, nothing else. "
        "2) Use git-style unified diffs (diff --git, --- a/path, +++ b/path, @@ hunks). "
        "3) Keep changes tight and focused on the described issue. "
        "4) Preserve code style and imports. "
        "5) If you cannot produce a safe patch, output an empty patch e.g. 'diff --git a/README.md b/README.md' with no hunks."
    )


def build_user_prompt(problem: dict, contexts: List[AffectedContext]) -> str:
    lines: List[str] = []
    lines.append(f"Problem ID: {problem.get('id')}")
    lines.append(f"Title: {problem.get('problem')}")
    lines.append("")
    lines.append("Requested Fix Guidance:")
    lines.append(problem.get("fix_prompt", "(none)").strip())
    lines.append("")
    lines.append("Relevant Files and Context:")
    for ctx in contexts:
        if ctx.path and ctx.snippet is not None:
            lines.append(f"- {ctx.ref}")
            # Use triple backticks with a language hint based on extension if desired
            ext = ctx.path.suffix.lower()
            lang = (
                "python"
                if ext in {".py", ".pyi"}
                else (
                    "conf"
                    if ext in {".conf", ".ini"}
                    else (
                        "dockerfile"
                        if ctx.path.name.lower() == "dockerfile"
                        else "yaml" if ext in {".yml", ".yaml"} else "text"
                    )
                )
            )
            lines.append(f"```{lang}")
            # Trim overly large snippets for token safety
            snippet = ctx.snippet
            max_chars = 12000
            if len(snippet) > max_chars:
                snippet = snippet[:max_chars] + "\n...\n"
            lines.append(snippet)
            lines.append("```")
        else:
            # Non-file notes or unresolved entries
            lines.append(f"- Note: {ctx.ref}")
    lines.append("")
    lines.append(
        "Provide ONLY a single fenced code block with a unified diff patch that applies cleanly from the repository root."
    )
    return "\n".join(lines)


def call_openai(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    """Call OpenAI Chat Completions and return the raw text content."""
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:  # pragma: no cover - library import
        raise RuntimeError(
            "The 'openai' package is required. Install with: pip install openai"
        ) from exc

    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
    )
    choice = resp.choices[0]
    content = choice.message.content or ""
    return content


DIFF_FENCE_RE = re.compile(r"```(?:diff|patch)?\s*\n([\s\S]*?)\n```", re.IGNORECASE)


def extract_patch_from_markdown(md: str) -> Optional[str]:
    """Extract the first fenced code block as the patch body.
    Accepts ```diff or ```patch or just triple backticks.
    """
    m = DIFF_FENCE_RE.search(md)
    if m:
        return m.group(1).strip()
    # Fallback: if there's no fence, but content looks like a diff, return all
    if md.lstrip().startswith("diff --git "):
        return md.strip()
    return None


def write_text(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


def git_apply_patch(
    patch_path: Path, check_only: bool = False
) -> subprocess.CompletedProcess:
    args = ["git", "apply", "--index", "--whitespace=fix"]
    if check_only:
        args.append("--check")
    args.append(str(patch_path))
    return subprocess.run(  # nosec B603 - controlled git command
        args, capture_output=True, text=True
    )


def file_paths_from_patch(patch: str) -> List[str]:
    paths: List[str] = []
    for line in patch.splitlines():
        # look for lines like: diff --git a/src/app.py b/src/app.py
        if line.startswith("diff --git "):
            parts = line.strip().split()
            if len(parts) >= 4:
                b_path = parts[3]
                if b_path.startswith("b/"):
                    paths.append(b_path[2:])
    return paths


def run_pre_commit_on_files(
    files: Iterable[str],
) -> Optional[subprocess.CompletedProcess]:
    files = [f for f in files if f]
    if not files:
        return None
    import shutil

    if shutil.which("pre-commit") is None:
        return None
    cmd = ["pre-commit", "run", "--files", *files]
    return subprocess.run(  # nosec B603 - controlled pre-commit command
        cmd, capture_output=True, text=True
    )


# -------- Main flow --------


def process_problem(
    problem: dict,
    repo_root: Path,
    out_dir: Path,
    *,
    api_key: str,
    model: str,
    apply: bool,
    run_pre_commit: bool,
) -> None:
    problem_id = problem.get("id")
    title = problem.get("problem")
    affected = problem.get("affected_files", []) or []

    eprint(f"\n== Problem {problem_id}: {title} ==")
    contexts = [resolve_affected_item(item, repo_root) for item in affected]
    user_prompt = build_user_prompt(problem, contexts)

    system_prompt = build_system_prompt()
    raw = call_openai(
        api_key=api_key,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    patch = extract_patch_from_markdown(raw)
    if not patch:
        eprint("No patch found in model response; saving raw output for review.")
        write_text(out_dir / f"problem_{problem_id}_response.txt", raw)
        return

    patch_path = out_dir / f"problem_{problem_id}.patch"
    write_text(patch_path, patch + "\n")
    eprint(f"Saved patch -> {patch_path}")

    if apply:
        check = git_apply_patch(patch_path, check_only=True)
        if check.returncode != 0:
            eprint("git apply --check failed; not applying.")
            eprint(check.stderr.strip())
            return
        apply_res = git_apply_patch(patch_path, check_only=False)
        if apply_res.returncode != 0:
            eprint("git apply failed:")
            eprint(apply_res.stderr.strip())
            return
        eprint("Patch applied successfully.")

        if run_pre_commit:
            changed_files = file_paths_from_patch(patch)
            if changed_files:
                eprint("Running pre-commit on changed files...")
                pc = run_pre_commit_on_files(changed_files)
                if pc:
                    if pc.returncode == 0:
                        eprint("pre-commit: OK")
                    else:
                        eprint("pre-commit reported issues:")
                        eprint(pc.stdout)
                        eprint(pc.stderr)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def detect_problem_container(data: dict) -> Tuple[str, List[Dict]]:
    """Return (container_name, problems_list) from various formats.

    Supports objects like {"<category>_problems": {"problems": [...]}}
    or a direct {"problems": [...]} at root.
    """
    # Direct root problems
    if isinstance(data.get("problems"), list):
        return "problems", data["problems"]

    # Find first key that endswith '_problems' with 'problems' list inside
    for k, v in data.items():
        if (
            isinstance(v, dict)
            and k.endswith("_problems")
            and isinstance(v.get("problems"), list)
        ):
            return k, v["problems"]

    # Fallback: find any dict containing list under 'problems'
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(v.get("problems"), list):
            return k, v["problems"]

    raise ValueError("Invalid JSON format: could not find a 'problems' list")


def iter_selected_problems(data: dict, ids: Optional[List[int]]) -> Iterable[dict]:
    _container, problems = detect_problem_container(data)
    if ids:
        id_set = set(int(x) for x in ids)
        yield from (p for p in problems if int(p.get("id")) in id_set)
    else:
        yield from problems


def discover_categories(
    repo_root: Path, requested: Optional[List[str]] = None
) -> List[str]:
    """Discover categories by scanning for '*_problems*.json' files in repo root.

    If 'requested' is provided, return it (lowercased, unique) filtered to those
    that have at least one matching file.
    """
    present: Dict[str, List[Path]] = {}
    for p in repo_root.glob("*_problems*.json"):
        name = p.name
        m = re.match(r"^(?P<cat>[a-zA-Z0-9_]+)_problems(?:_batch\d+)?\.json$", name)
        if not m:
            continue
        cat = m.group("cat").lower()
        present.setdefault(cat, []).append(p)

    if requested:
        req = []
        for c in requested:
            c2 = c.strip().lower()
            if c2 and c2 not in req:
                req.append(c2)
        return [c for c in req if c in present]

    # Default: use all discovered categories, sorted
    return sorted(present.keys())


def discover_files_for_category(repo_root: Path, category: str) -> List[Path]:
    """Return JSON files for a category, respecting the naming convention.

    Prefer '{category}_problems.json' for batch 1; if absent, accept
    '{category}_problems_batch1.json' as fallback. Then include
    '{category}_problems_batchN.json' for N>=2 as they exist. The results are
    returned in ascending batch order.
    """
    results: List[Path] = []
    p0 = repo_root / f"{category}_problems.json"
    p1 = repo_root / f"{category}_problems_batch1.json"
    if p0.exists():
        results.append(p0)
    elif p1.exists():
        results.append(p1)

    # Include batch2+
    for n in range(2, 100):
        pn = repo_root / f"{category}_problems_batch{n}.json"
        if pn.exists():
            results.append(pn)
        else:
            # Stop at first gap to avoid long scans
            break

    # If neither p0 nor p1 existed, fall back to any globbed matches (sorted)
    if not results:
        results = sorted(repo_root.glob(f"{category}_problems_batch*.json"))

    return results


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply known fixes via OpenAI across categories"
    )
    parser.add_argument(
        "--categories",
        nargs="*",
        help=(
            "Optional list of categories to process (default: auto-discover). "
            "Examples: security architecture performance operations code_quality compliance"
        ),
    )
    parser.add_argument(
        "--ids",
        type=int,
        nargs="*",
        help="Optional list of problem IDs to process within each JSON (default: all)",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        help="OpenAI model name (default: env OPENAI_MODEL or gpt-4o-mini)",
    )
    parser.add_argument(
        "--out-dir",
        default="out/known_fixes",
        help="Directory to write model outputs and patches",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="If set, attempt to git-apply the returned patches",
    )
    parser.add_argument(
        "--no-pre-commit",
        action="store_true",
        help="Skip running pre-commit on changed files after applying",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    repo_root = Path.cwd()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        eprint("ERROR: OPENAI_API_KEY is not set in the environment.")
        return 2

    categories = discover_categories(repo_root, args.categories)
    if not categories:
        eprint(
            "No categories discovered. Ensure '*_problems*.json' files exist in repo root."
        )
        return 2

    total_problems = 0
    processed_problems = 0
    for cat in categories:
        files = discover_files_for_category(repo_root, cat)
        if not files:
            continue
        eprint(f"\n== Category: {cat} | Files: {len(files)} ==")
        for jf in files:
            try:
                data = load_json(jf)
            except Exception as exc:
                eprint(f"Failed to read {jf.name}: {exc}")
                continue

            problems = list(iter_selected_problems(data, args.ids))
            total_problems += len(problems)
            if not problems:
                eprint(f"No problems selected in {jf.name}.")
                continue

            eprint(
                f"Processing {len(problems)} problem(s) in {jf.name} using model '{args.model}' (apply={args.apply})"
            )
            out_dir = Path(args.out_dir) / cat / jf.stem
            out_dir.mkdir(parents=True, exist_ok=True)
            for p in problems:
                try:
                    process_problem(
                        p,
                        repo_root,
                        out_dir,
                        api_key=api_key,
                        model=args.model,
                        apply=bool(args.apply),
                        run_pre_commit=not args.no_pre_commit,
                    )
                    processed_problems += 1
                except Exception as exc:
                    eprint(f"Problem {p.get('id')} in {jf.name} failed: {exc}")

    eprint(f"\nDone. Processed {processed_problems}/{total_problems} problem(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
