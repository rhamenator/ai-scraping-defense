import argparse
import json
import os
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request

from pr_claims import (
    CLAIMS_DEFAULT_PATH,
    detect_claim_conflicts,
    load_claims,
    normalize_file_path,
    record_claim,
    release_claims,
)

# Configuration
PROBLEMS_DIR = "."
API_KEY = os.environ.get("GEMINI_API_KEY")
DB_FILE = "problem_file_map.db"
JSON_FILE = "problem_file_map.json"


def call_gemini(prompt):
    """Calls Gemini API to generate content."""
    if not API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable not set.")

    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}

    # List of models to try in order
    models = ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-flash-latest", "gemini-pro"]

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}"
        try:
            req = urllib.request.Request(
                url, data=json.dumps(data).encode("utf-8"), headers=headers
            )
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode("utf-8"))
                if "candidates" in result and result["candidates"]:
                    return result["candidates"][0]["content"]["parts"][0]["text"]
                return None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue  # Try next model
            print(f"Model {model} failed: {e}")
        except Exception as e:
            print(f"Error with {model}: {e}")

    print("All models failed.")
    return None


def get_problem_metadata(title):
    """Get metadata from database."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT category, severity, confidence, fix_prompt, pr_created, pr_number
            FROM problems WHERE title = ?
        """,
            (title,),
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "category": row[0],
                "severity": row[1],
                "confidence": row[2],
                "fix_prompt": row[3],
                "pr_created": bool(row[4]),
                "pr_number": row[5],
            }
    except Exception as e:
        print(f"Error loading metadata from DB: {e}")
    return None


def update_pr_tracking(title, pr_number):
    """Update pr_created and pr_number in database and JSON."""
    try:
        # Update database
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE problems
            SET pr_created = 1, pr_number = ?
            WHERE title = ?
        """,
            (pr_number, title),
        )
        conn.commit()
        conn.close()

        # Update JSON
        with open(JSON_FILE, "r") as f:
            data = json.load(f)

        if title in data:
            data[title]["pr_created"] = True
            data[title]["pr_number"] = pr_number

            with open(JSON_FILE, "w") as f:
                json.dump(data, f, indent=2)

        print(f"  Updated PR tracking: #{pr_number}")
    except Exception as e:
        print(f"  Error updating PR tracking: {e}")


def get_file_content(filepath):
    try:
        # Remove (Proposed) marker
        clean_path = filepath.replace(" (Proposed)", "").strip()
        clean_path = clean_path.split(":")[0].strip()

        # Remove leading slash if present (e.g. /d:/...)
        if clean_path.startswith("/") and ":" in clean_path:
            clean_path = clean_path.lstrip("/")

        # Handle relative paths if needed, but usually they are relative to root
        if os.path.exists(clean_path):
            with open(clean_path, "r", encoding="utf-8") as f:
                return f.read()
        else:
            # Try to find it? No, assume paths are correct from issue
            pass
    except Exception as e:
        print(f"Error reading file {filepath}: {e}")
    return None


def generate_fix_and_metadata(title, description, fix_prompt, file_contents):
    prompt = f"""
You are an expert secure code fixing assistant.
I have a problem description and the content of the affected file(s).
Your task is to:
1. Analyze the problem.
2. Fix the code in the provided file(s) OR create new files if needed.
3. Provide your detailed explanation of changes.

Problem: {title}
Description: {description}
Fix Instruction: {fix_prompt}

Files:
"""
    for path, content in file_contents.items():
        if content == "(This is a new file to be created)":
            prompt += (
                f"\n--- CREATE NEW FILE: {path} ---\n"
                "(Design and implement this file from scratch based on the fix instructions)\n"
            )
        else:
            prompt += (
                f"\n--- START FILE: {path} ---\n"
                f"{content}\n--- END FILE: {path} ---\n"
            )

    prompt += """
Output Format:
Please provide the response in strict JSON format as follows:
{
    "explanation": "Brief explanation of changes...",
    "files": {
        "path/to/file1": "Full corrected content of file1...",
        "path/to/file2": "Full corrected content of file2..."
    }
}
Do not include markdown formatting (```json) in the response, just the raw JSON string.
"""
    return call_gemini(prompt)


def ensure_label(label, color="ededed"):
    try:
        subprocess.run(  # nosec B603 - controlled gh CLI call
            ["gh", "label", "create", label, "--color", color, "--force"],
            check=False,
            capture_output=True,
        )
    except Exception:
        pass


def fetch_gh_issues(limit=1):
    print(f"Fetching top {limit} open issues from GitHub...")
    cmd = [
        "gh",
        "issue",
        "list",
        "--state",
        "open",
        "--json",
        "number,title,body",
        "--limit",
        str(limit),
    ]
    result = subprocess.run(  # nosec B603 - controlled gh CLI call
        cmd, capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Failed to fetch issues: {result.stderr}")
        return []
    return json.loads(result.stdout)


def fetch_single_issue(issue_number):
    print(f"Fetching issue #{issue_number} from GitHub...")
    cmd = ["gh", "issue", "view", str(issue_number), "--json", "number,title,body"]
    result = subprocess.run(  # nosec B603 - controlled gh CLI call
        cmd, capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"Failed to fetch issue #{issue_number}: {result.stderr}")
        return []
    try:
        issue = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"Failed to parse GitHub response: {exc}")
        return []
    return [issue]


def parse_affected_files(body):
    files = []
    # Look for "Affected/Target Files" sections followed by list items
    markers = {
        "**Affected Files**",
        "**Target Files**",
        "## Affected Files",
        "## Target Files",
    }
    lines = body.split("\n")
    in_files_section = False
    for raw_line in lines:
        line = raw_line.strip()
        if any(marker in line for marker in markers):
            in_files_section = True
            continue
        if not in_files_section:
            continue
        if not line:
            # blank line ends section
            in_files_section = False
            continue
        if line.startswith("#") and not line.startswith("- "):
            in_files_section = False
            continue
        if line.startswith("- "):
            files.append(line[2:].strip())
    return files


def create_pr(issue, fix_data, metadata, dry_run=False):
    title = issue["title"]
    issue_number = issue["number"]
    category = metadata["category"]
    severity = metadata["severity"]
    confidence = metadata["confidence"]

    slug = "".join(c if c.isalnum() else "-" for c in title.lower())[:50]
    branch_name = f"fix/issue-{issue_number}-{slug}-{int(time.time())}"

    print(f"Preparing PR for Issue #{issue_number}: {title}")

    if dry_run:
        print("  [Dry Run] Would generate fix content using Gemini API.")
        print(f"  [Dry Run] Would create branch: {branch_name}")
        if fix_data and fix_data.get("files"):
            print("  [Dry Run] Would update the following files:")
            for path in fix_data["files"].keys():
                print(f"    - {path}")
        else:
            print(
                "  [Dry Run] No file changes detected yet (likely due to skipped LLM call)."
            )
        print(
            "  [Dry Run] Would commit and push branch to origin, then create PR assigning to @me."
        )
        return None, branch_name

    # Create Branch
    subprocess.run(  # nosec B603 - controlled git command
        ["git", "checkout", "-b", branch_name], check=True
    )

    # Apply Changes
    files_changed = []
    for path, new_content in fix_data["files"].items():
        clean_path = path.replace(" (Proposed)", "").strip()
        clean_path = clean_path.split(":")[0].strip()
        if clean_path.startswith("/") and ":" in clean_path:
            clean_path = clean_path.lstrip("/")

        try:
            # Ensure dir exists
            if os.path.dirname(clean_path):
                os.makedirs(os.path.dirname(clean_path), exist_ok=True)
            with open(clean_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            subprocess.run(  # nosec B603 - controlled git command
                ["git", "add", clean_path], check=True
            )
            files_changed.append(clean_path)
        except Exception as e:
            print(f"Failed to write {clean_path}: {e}")

    if not files_changed:
        print("No files changed. Skipping PR.")
        subprocess.run(  # nosec B603 - controlled git command
            ["git", "checkout", "-"], check=True
        )
        subprocess.run(  # nosec B603 - controlled git command
            ["git", "branch", "-D", branch_name], check=True
        )
        return None, branch_name

    # Commit
    subprocess.run(  # nosec B603 - controlled git command
        ["git", "commit", "-m", f"Fix: {title} (Issue #{issue_number})"], check=True
    )

    # Push
    subprocess.run(  # nosec B603 - controlled git command
        ["git", "push", "origin", branch_name], check=True
    )

    # Create Labels
    ensure_label(category, "1d76db")  # Blue for category

    # Severity labels with colors
    severity_colors = {"High": "d73a4a", "Medium": "fbca04", "Low": "0e8a16"}
    ensure_label(severity, severity_colors.get(severity, "ededed"))

    # Confidence labels
    if confidence >= 0.75:
        confidence_label = "High Confidence"
        confidence_color = "0e8a16"  # Green
    elif confidence >= 0.5:
        confidence_label = "Medium Confidence"
        confidence_color = "fbca04"  # Yellow
    else:
        confidence_label = "Low Confidence"
        confidence_color = "d73a4a"  # Red

    ensure_label(confidence_label, confidence_color)
    ensure_label("automated-pr", "ededed")

    # Create PR
    body = f"""
## Automated Fix
**Problem**: {title}
**Category**: {category}
**Severity**: {severity}
**Confidence**: {confidence:.2f} ({confidence_label})

### Explanation
{fix_data.get('explanation', 'No explanation provided.')}

### Verification
Auto-generated fix. Please review carefully.

Fixes #{issue_number}
"""

    cmd = [
        "gh",
        "pr",
        "create",
        "--title",
        f"[{category}] [{severity}] {title}",
        "--body",
        body,
        "--label",
        f"{category},{severity},{confidence_label},automated-pr",
        "--assignee",
        "@me",
        "--base",
        "main",
    ]

    try:
        result = subprocess.run(  # nosec B603 - controlled gh CLI call
            cmd, check=True, capture_output=True, text=True
        )
        print(f"PR Created successfully for Issue #{issue_number}")

        # Extract PR number from output
        pr_url = result.stdout.strip()
        pr_number = int(pr_url.split("/")[-1]) if pr_url else None

        if pr_number:
            update_pr_tracking(title, pr_number)

        return pr_number, branch_name
    except subprocess.CalledProcessError as e:
        print(f"Failed to create PR: {e}")
        return None, branch_name
    finally:
        # Cleanup
        subprocess.run(  # nosec B603 - controlled git command
            ["git", "checkout", "-"], check=True
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--smoke-test", action="store_true", help="Run for 1 issue from GH"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of issues to fetch and process",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the workflow without creating branches or PRs",
    )
    parser.add_argument(
        "--issue-number", type=int, help="Process a specific GitHub issue number"
    )
    parser.add_argument(
        "--claims-file",
        default=CLAIMS_DEFAULT_PATH,
        help="Path to file tracking active PR file claims",
    )
    parser.add_argument(
        "--release-branch",
        action="append",
        help="Release file claims for the specified branch. May be passed multiple times.",
    )
    args = parser.parse_args()

    limit = 1 if args.smoke_test else (args.limit if args.limit > 0 else 1000)

    claims = load_claims(args.claims_file)

    if args.release_branch:
        claims = release_claims(claims, args.claims_file, args.release_branch)

    # Fetch issues
    if args.issue_number:
        issues = fetch_single_issue(args.issue_number)
    else:
        issues = fetch_gh_issues(limit)
    print(f"Fetched {len(issues)} issues to process.")

    for issue in issues:
        title = issue["title"]
        print(f"\nProcessing Issue #{issue['number']}: {title}")

        # Get metadata from database
        metadata = get_problem_metadata(title)
        if not metadata:
            print("  No metadata found. Skipping.")
            continue

        if metadata["pr_created"]:
            message = f"  PR already created: #{metadata['pr_number']}."
            if args.dry_run:
                print(f"{message} Including in dry run output only.")
            else:
                print(f"{message} Skipping.")
                continue

        print(f"  Category: {metadata['category']}")
        print(f"  Severity: {metadata['severity']}")
        print(f"  Confidence: {metadata['confidence']:.2f}")

        # Parse affected files
        affected_files = parse_affected_files(issue["body"])
        if not affected_files:
            print("  No affected files found. Skipping.")
            continue

        # Read file contents
        file_contents = {}
        for path in affected_files:
            if "(Proposed)" in path:
                # New file to create
                clean_path = path.replace(" (Proposed)", "").strip()
                file_contents[clean_path] = "(This is a new file to be created)"
            else:
                content = get_file_content(path)
                if content:
                    file_contents[path] = content

        if not file_contents:
            print("  Could not read any affected files. Skipping.")
            continue

        normalized_targets = [
            normalize_file_path(path) for path in file_contents.keys()
        ]
        conflicts = detect_claim_conflicts(claims, normalized_targets)
        if conflicts:
            print("  File claims conflict with existing automation branches:")
            for conflict in conflicts:
                files_list = ", ".join(conflict["files"])
                issue_ref = conflict.get("issue")
                issue_text = f"Issue #{issue_ref}" if issue_ref else "Unknown issue"
                print(
                    f"    - Branch {conflict['branch']} ({issue_text}) => {files_list}"
                )
            if args.dry_run:
                print("  [Dry Run] Would skip due to active file claims.")
            else:
                print("  Skipping issue due to active file claims.")
            continue

        print(f"  Processing {len(file_contents)} files...")

        if args.dry_run:
            slug = "".join(c if c.isalnum() else "-" for c in title.lower())[:50]
            branch_name = f"fix/issue-{issue['number']}-{slug}-{int(time.time())}"
            print("  [Dry Run] Skipping LLM call and PR creation.")
            print(f"  [Dry Run] Would create branch: {branch_name}")
            print("  [Dry Run] Would modify these files:")
            for path in file_contents.keys():
                print(f"    - {path}")
            if metadata["pr_created"]:
                print(
                    "  [Dry Run] Note: PR already exists; dry run does not alter tracking state."
                )
            if args.smoke_test:
                print("\nDry run smoke test complete. Stopping.")
                break
            continue

        # Generate Fix
        print("  Generating fix...")
        try:
            response = generate_fix_and_metadata(
                title, issue["body"], metadata["fix_prompt"], file_contents
            )
            if not response:
                print("  Failed to get fix from LLM.")
                continue

            response = response.replace("```json", "").replace("```", "").strip()
            fix_data = json.loads(response)

            # Create PR
            pr_number, branch_name = create_pr(issue, fix_data, metadata, dry_run=False)

            if pr_number:
                claims = record_claim(
                    claims,
                    args.claims_file,
                    branch_name,
                    issue["number"],
                    normalized_targets,
                )

            if args.smoke_test:
                print("\nSmoke test complete. Stopping.")
                break

            time.sleep(5)

        except Exception as e:
            print(f"  Error processing issue: {e}")
            import traceback

            traceback.print_exc()
            if args.smoke_test:
                print("Error during smoke test. Stopping.")
                break


if __name__ == "__main__":
    main()
