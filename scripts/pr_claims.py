import json
import os
from datetime import datetime
from typing import Dict, Iterable, List, Optional

CLAIMS_DEFAULT_PATH = os.path.join("automation", "pr_file_claims.json")


def normalize_file_path(path: str) -> str:
    clean_path = path.replace(" (Proposed)", "").strip()
    clean_path = clean_path.split(":")[0].strip()
    if clean_path.startswith("/") and ":" in clean_path:
        clean_path = clean_path.lstrip("/")
    clean_path = os.path.normpath(clean_path)
    return clean_path.replace("\\", "/")


def load_claims(path: Optional[str]) -> Dict[str, Dict[str, object]]:
    if not path:
        return {}
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if isinstance(raw, dict):
            return raw
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Failed to load claims file {path}: {exc}")
    return {}


def save_claims(path: Optional[str], claims: Dict[str, Dict[str, object]]) -> None:
    if not path:
        return
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(claims, handle, indent=2, sort_keys=True)


def detect_claim_conflicts(
    claims: Dict[str, Dict[str, object]],
    target_files: Iterable[str],
    *,
    ignore_branch: Optional[str] = None,
) -> List[Dict[str, object]]:
    conflicts: List[Dict[str, object]] = []
    target_set = set(target_files)
    for branch, entry in claims.items():
        if branch == ignore_branch:
            continue
        claimed_files = set(entry.get("files", []))
        overlap = sorted(target_set & claimed_files)
        if overlap:
            conflicts.append(
                {
                    "branch": branch,
                    "issue": entry.get("issue"),
                    "files": overlap,
                }
            )
    return conflicts


def record_claim(
    claims: Dict[str, Dict[str, object]],
    path: Optional[str],
    branch: str,
    issue_identifier: Optional[int],
    files: Iterable[str],
) -> Dict[str, Dict[str, object]]:
    claims[branch] = {
        "issue": issue_identifier,
        "files": sorted(set(files)),
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    save_claims(path, claims)
    print(f"  Recorded file claims for branch {branch}.")
    return claims


def release_claims(
    claims: Dict[str, Dict[str, object]],
    path: Optional[str],
    branches: Iterable[str],
) -> Dict[str, Dict[str, object]]:
    modified = False
    for branch in branches:
        if branch in claims:
            del claims[branch]
            print(f"Released claims for branch {branch}.")
            modified = True
    if modified:
        save_claims(path, claims)
    return claims
