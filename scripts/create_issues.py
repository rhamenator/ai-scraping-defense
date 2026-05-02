import argparse
import json
import os
import subprocess
import time
from collections import defaultdict

# Configuration
PROBLEMS_DIR = "."
ISSUES_FILE = "ISSUES_TO_CREATE.md"
RATE_LIMIT_SLEEP = 5  # Seconds between requests


def parse_json_files():
    problems = []
    for filename in os.listdir(PROBLEMS_DIR):
        if filename.endswith(".json") and "problems" in filename:
            try:
                with open(os.path.join(PROBLEMS_DIR, filename), "r") as f:
                    data = json.load(f)
                    # Handle different structures if necessary, assuming common structure based on file view
                    # Structure seen: {"security_problems": {"problems": [...]}}
                    # or just list of problems? Let's inspect the file content we saw.
                    # security_problems_batch1.json had {"security_problems": {"problems": [...]}}

                    for key in data:
                        if isinstance(data[key], dict) and "problems" in data[key]:
                            problems.extend(data[key]["problems"])
                        elif key == "problems" and isinstance(data[key], list):
                            problems.extend(data[key])
            except Exception as e:
                print(f"Error parsing {filename}: {e}")
    return problems


def parse_problems_txt():
    # problems.txt seems to be a JSON array of objects, but maybe malformed or just a list of dicts
    # Based on view_file output, it looked like `[][{...},{...}]` which is weird,
    # or maybe just `[{...}, {...}]`.
    # Let's try to parse it as strict JSON first, if fails, try manual parsing.
    # The view_file showed: `[][{...` at the start? No, line 1 was `[][{`.
    # That looks like some weird dump.
    # Let's skip problems.txt for now if it's messy, or try to clean it.
    # Actually, let's try to read it and see if we can salvage it.
    problems = []
    if os.path.exists("problems.txt"):
        try:
            with open("problems.txt", "r") as f:
                f.read()
                # Attempt to fix common issues if it's not valid JSON
                # If it starts with `[][`, it might be a concatenation of dumps.
                # Let's try to find JSON objects.
                # For now, let's assume it might be valid or we skip it if it fails.
                # The file view showed `[][{...}]`. This is valid JSON if it's a list containing a list and a list of objects?
                # No, `[]` is an empty list. `[{...}]` is a list.
                # `[][{...}]` is invalid JSON.
                pass
        except Exception as exc:
            print(f"Warning: failed to parse problems.txt: {exc}")
    return problems


def group_problems(problems):
    grouped = defaultdict(
        lambda: {
            "affected_files": [],
            "description": "",
            "severity": "",
            "fix_prompt": "",
        }
    )

    for p in problems:
        # Key by problem title/name
        title = p.get("problem") or p.get(
            "message"
        )  # 'problem' in json, 'message' in txt
        if not title:
            continue

        key = title

        # Merge data
        if "affected_files" in p:
            grouped[key]["affected_files"].extend(p["affected_files"])
        if "resource" in p:  # from problems.txt
            grouped[key]["affected_files"].append(
                f"{p['resource']}:{p.get('startLineNumber')}"
            )

        if not grouped[key]["description"]:
            grouped[key]["description"] = p.get("problem") or p.get("message")

        if not grouped[key]["fix_prompt"]:
            grouped[key]["fix_prompt"] = p.get("fix_prompt", "")

    return grouped


def check_if_issue_exists(title):
    """Checks if an issue with the same title exists (open or closed)."""
    try:
        # Search for issues with the title in the repo
        # --json title to just get titles and verify exact match if needed
        cmd = [
            "gh",
            "issue",
            "list",
            "--search",
            f"{title} in:title",
            "--state",
            "all",
            "--json",
            "title",
        ]
        result = subprocess.run(  # nosec B603 - controlled gh CLI call
            cmd, capture_output=True, text=True
        )
        if result.returncode == 0:
            issues = json.loads(result.stdout)
            # Check for exact match or close enough
            for issue in issues:
                if issue["title"] == title:
                    return True
        return False
    except Exception as e:
        print(f"Warning: Could not check for existing issue '{title}': {e}")
        return False


def create_markdown_report(grouped_problems):
    with open(ISSUES_FILE, "w") as f:
        f.write("# Outstanding Issues\n\n")
        for title, data in grouped_problems.items():
            f.write(f"## {title}\n\n")
            f.write(f"**Description**: {data['description']}\n\n")
            if data["fix_prompt"]:
                f.write(f"**Suggested Fix**: {data['fix_prompt']}\n\n")

            f.write("**Affected Files**:\n")
            for file in set(data["affected_files"]):
                f.write(f"- {file}\n")
            f.write("\n---\n\n")
    print(f"Report generated: {ISSUES_FILE}")


def upload_issues(grouped_problems):
    count = 0
    for title, data in grouped_problems.items():
        print(f"Processing: {title}")

        if check_if_issue_exists(title):
            print(f"  Skipping (Duplicate/Closed found): {title}")
            continue

        body = f"**Description**: {data['description']}\n\n"
        if data["fix_prompt"]:
            body += f"**Suggested Fix**: {data['fix_prompt']}\n\n"
        body += "**Affected Files**:\n"
        for file in set(data["affected_files"]):
            body += f"- {file}\n"

        try:
            cmd = [
                "gh",
                "issue",
                "create",
                "--title",
                title,
                "--body",
                body,
                "--label",
                "automated-issue",
            ]
            subprocess.run(cmd, check=True)  # nosec B603 - controlled gh CLI call
            print(f"  Created issue: {title}")
            count += 1
            time.sleep(RATE_LIMIT_SLEEP)
        except subprocess.CalledProcessError as e:
            print(f"  Failed to create issue {title}: {e}")

    print(f"Finished. Created {count} issues.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upload", action="store_true", help="Upload issues to GitHub")
    parser.add_argument(
        "--report",
        action="store_true",
        default=True,
        help="Generate Markdown report (default)",
    )
    args = parser.parse_args()

    print("Parsing problem files...")
    problems = parse_json_files()
    # problems.extend(parse_problems_txt()) # Skipping txt for now to avoid noise/errors

    print(f"Found {len(problems)} raw problems.")
    grouped = group_problems(problems)
    print(f"Grouped into {len(grouped)} unique issues.")

    if args.upload:
        print("Starting upload process...")
        upload_issues(grouped)
    else:
        create_markdown_report(grouped)


if __name__ == "__main__":
    main()
