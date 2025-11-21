import json
import os
import subprocess
import time
import argparse

# Configuration
PROBLEM_MAP_FILE = "problem_file_map.json"

def fetch_gh_issues(limit=1000):
    print(f"Fetching top {limit} open issues from GitHub...")
    # Sort by created desc to get newest first
    cmd = ["gh", "issue", "list", "--state", "open", "--search", "sort:created-desc", "--json", "number,title,body", "--limit", str(limit)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Failed to fetch issues: {result.stderr}")
        return []
    return json.loads(result.stdout)

def update_issue_body(issue_number, body, affected_files):
    print(f"Updating Issue #{issue_number}...")
    
    # Construct new section
    files_section = "\n\n**Affected Files**:\n" + "\n".join([f"- {f}" for f in affected_files])
    
    # Check if section exists
    if "**Affected Files**" in body:
        # Replace existing section (naive regex or split)
        # We want to keep everything before "**Affected Files**"
        parts = body.split("**Affected Files**")
        new_body = parts[0].strip() + files_section
    else:
        new_body = body.strip() + files_section
        
    # Update GitHub
    cmd = ["gh", "issue", "edit", str(issue_number), "--body", new_body]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"  Updated Issue #{issue_number}")
    except subprocess.CalledProcessError as e:
        print(f"  Failed to update Issue #{issue_number}: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Do not update GitHub")
    args = parser.parse_args()
    
    if not os.path.exists(PROBLEM_MAP_FILE):
        print(f"Error: {PROBLEM_MAP_FILE} not found. Run generate_problem_file_map.py first.")
        return

    print(f"Loading map from {PROBLEM_MAP_FILE}...")
    with open(PROBLEM_MAP_FILE, 'r') as f:
        problem_map = json.load(f)
        
    issues = fetch_gh_issues()
    print(f"Fetched {len(issues)} issues.")
    
    count = 0
    for issue in issues:
        title = issue['title']
        if title in problem_map:
            data = problem_map[title]
            resolved_files = data.get("resolved_files", [])
            
            if resolved_files:
                print(f"Match: #{issue['number']} - {title}")
                print(f"  Files: {resolved_files}")
                
                if not args.dry_run:
                    update_issue_body(issue['number'], issue['body'], resolved_files)
                    time.sleep(1) # Rate limit
                count += 1
            else:
                print(f"Skipping #{issue['number']} (No resolved files in map)")
        else:
            # print(f"No map entry for: {title}")
            pass
            
    print(f"Processed {count} issues.")

if __name__ == "__main__":
    main()
