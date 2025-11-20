import json
import os
import subprocess
import time
import argparse
import sys
import urllib.request
import urllib.error
import re
import sqlite3

# Configuration
PROBLEMS_DIR = "."
API_KEY = os.environ.get("GEMINI_API_KEY")
DB_FILE = "problem_file_map.db"
JSON_FILE = "problem_file_map.json"

def call_gemini(prompt):
    """Calls Gemini API to generate content."""
    if not API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable not set.")
        
    headers = {'Content-Type': 'application/json'}
    data = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    # List of models to try in order
    models = [
        "gemini-2.0-flash",
        "gemini-1.5-pro",
        "gemini-flash-latest",
        "gemini-pro"
    ]
    
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={API_KEY}"
        try:
            req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers=headers)
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                if "candidates" in result and result["candidates"]:
                    return result["candidates"][0]["content"]["parts"][0]["text"]
                return None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue # Try next model
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
        cursor.execute("""
            SELECT category, severity, confidence, fix_prompt, pr_created, pr_number
            FROM problems WHERE title = ?
        """, (title,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "category": row[0],
                "severity": row[1],
                "confidence": row[2],
                "fix_prompt": row[3],
                "pr_created": bool(row[4]),
                "pr_number": row[5]
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
        cursor.execute("""
            UPDATE problems 
            SET pr_created = 1, pr_number = ?
            WHERE title = ?
        """, (pr_number, title))
        conn.commit()
        conn.close()
        
        # Update JSON
        with open(JSON_FILE, 'r') as f:
            data = json.load(f)
        
        if title in data:
            data[title]["pr_created"] = True
            data[title]["pr_number"] = pr_number
            
            with open(JSON_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        
        print(f"  Updated PR tracking: #{pr_number}")
    except Exception as e:
        print(f"  Error updating PR tracking: {e}")

def get_file_content(filepath):
    try:
        # Remove (Proposed) marker
        clean_path = filepath.replace(" (Proposed)", "").strip()
        clean_path = clean_path.split(':')[0].strip()
        
        # Remove leading slash if present (e.g. /d:/...)
        if clean_path.startswith('/') and ':' in clean_path:
             clean_path = clean_path.lstrip('/')
        
        # Handle relative paths if needed, but usually they are relative to root
        if os.path.exists(clean_path):
            with open(clean_path, 'r', encoding='utf-8') as f:
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

TONE AND STYLE INSTRUCTIONS:
- Write in a style that is objective, clear, professional, and authoritative.
- Avoid "marketing speak", over-enthusiasm, or awkward phrasing (e.g., no "This update seamlessly integrates...").
- Be direct and factual about what was fixed and why.
- Use simple, clear English.
- Keep the explanation concise (under 200 words).

CRITICAL FORMATTING RULES FOR MARKDOWN FILES:
- ALL code blocks MUST use triple backticks with language identifier
- Format: ```language followed by code, then closing ```
- Example: ```python for Python code, ```bash for shell scripts, etc.
- Never leave code blocks without proper fencing
- This prevents markdown linting errors

Problem: {title}
Description: {description}
Fix Instruction: {fix_prompt}

Files:
"""
    for path, content in file_contents.items():
        if content == "(This is a new file to be created)":
            prompt += f"\n--- CREATE NEW FILE: {path} ---\n(Design and implement this file from scratch based on the fix instructions)\n"
        else:
            prompt += f"\n--- START FILE: {path} ---\n{content}\n--- END FILE: {path} ---\n"

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
Ensure the JSON is valid and properly escaped.

REMEMBER: If modifying .md files, ensure ALL code blocks use proper fencing with language identifiers!
"""
    return call_gemini(prompt)

def ensure_label(label, color="ededed"):
    try:
        subprocess.run(["gh", "label", "create", label, "--color", color, "--force"], 
                       check=False, capture_output=True)
    except:
        pass

def fetch_gh_issues(limit=1, issue_number=None):
    if issue_number:
        print(f"Fetching issue #{issue_number} from GitHub...")
        cmd = ["gh", "issue", "view", str(issue_number), "--json", "number,title,body"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Failed to fetch issue #{issue_number}: {result.stderr}")
            return []
        return [json.loads(result.stdout)]
    
    print(f"Fetching top {limit} open issues from GitHub...")
    cmd = ["gh", "issue", "list", "--state", "open", "--json", "number,title,body", "--limit", str(limit)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Failed to fetch issues: {result.stderr}")
        return []
    return json.loads(result.stdout)

def parse_affected_files(body):
    files = []
    # Look for "**Affected Files**:" followed by list items
    if "**Affected Files**" in body:
        lines = body.split('\n')
        in_files_section = False
        for line in lines:
            if "**Affected Files**" in line:
                in_files_section = True
                continue
            if in_files_section:
                if line.strip().startswith('- '):
                    files.append(line.strip()[2:].strip())
                elif line.strip() == "" or line.startswith('#') or line.startswith('*'):
                    # End of section? Maybe.
                    pass
    return files

def create_pr(issue, fix_data, metadata):
    title = issue['title']
    issue_number = issue['number']
    category = metadata['category']
    severity = metadata['severity']
    confidence = metadata['confidence']
    
    slug = "".join(c if c.isalnum() else "-" for c in title.lower())[:50]
    branch_name = f"fix/issue-{issue_number}-{slug}-{int(time.time())}"
    
    print(f"Preparing PR for Issue #{issue_number}: {title}")
    
    # Capture current branch
    try:
        original_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
    except:
        original_branch = "main" # Fallback

    try:
        # Create Branch
        subprocess.run(["git", "checkout", "-b", branch_name], check=True)
        
        # Apply Changes
        files_changed = []
        for path, new_content in fix_data["files"].items():
            clean_path = path.replace(" (Proposed)", "").strip()
            clean_path = clean_path.split(':')[0].strip()
            if clean_path.startswith('/') and ':' in clean_path: clean_path = clean_path.lstrip('/')
                
            try:
                # Ensure dir exists
                if os.path.dirname(clean_path):
                    os.makedirs(os.path.dirname(clean_path), exist_ok=True)
                with open(clean_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                subprocess.run(["git", "add", clean_path], check=True)
                files_changed.append(clean_path)
            except Exception as e:
                print(f"Failed to write {clean_path}: {e}")
                
        if not files_changed:
            print("No files changed. Skipping PR.")
            return None

        # Commit
        subprocess.run(["git", "commit", "-m", f"Fix: {title} (Issue #{issue_number})"], check=True)
        
        # Push
        subprocess.run(["git", "push", "origin", branch_name], check=True)
        
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
            "gh", "pr", "create",
            "--title", f"[{category}] [{severity}] {title}",
            "--body", body,
            "--label", f"{category},{severity},{confidence_label},automated-pr",
            "--assignee", "@me",
            "--base", "main"
        ]
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"PR Created successfully for Issue #{issue_number}")
            
            # Extract PR number from output
            pr_url = result.stdout.strip()
            pr_number = int(pr_url.split('/')[-1]) if pr_url else None
            
            if pr_number:
                print(f"  Linked Issue #{issue_number} to new PR #{pr_number}")
                update_pr_tracking(title, pr_number)
            
            return pr_number
        except subprocess.CalledProcessError as e:
            print(f"Failed to create PR: {e}")
            return None
            
    except Exception as e:
        print(f"Error during PR creation process: {e}")
        return None
    finally:
        # Cleanup: Always go back to original branch
        print(f"Returning to branch: {original_branch}")
        subprocess.run(["git", "checkout", original_branch], check=False)
        # Optional: delete the feature branch locally if we want to save space/clutter
        # subprocess.run(["git", "branch", "-D", branch_name], check=False)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true", help="Run for 1 issue from GH")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--issue-number", type=int, help="Target specific issue number")
    args = parser.parse_args()
    
    limit = 10 if args.smoke_test else (args.limit if args.limit > 0 else 1000)
    
    # Fetch issues
    issues = fetch_gh_issues(limit, args.issue_number)
    print(f"Fetched {len(issues)} issues to process.")
    
    for issue in issues:
        title = issue['title']
        print(f"\nProcessing Issue #{issue['number']}: {title}")
        
        # Get metadata from database
        metadata = get_problem_metadata(title)
        if not metadata:
            print("  No metadata found. Skipping.")
            continue
        
        if metadata['pr_created']:
            print(f"  PR already created: #{metadata['pr_number']}. Skipping.")
            continue
        
        print(f"  Category: {metadata['category']}")
        print(f"  Severity: {metadata['severity']}")
        print(f"  Confidence: {metadata['confidence']:.2f}")
        
        # Parse affected files
        affected_files = parse_affected_files(issue['body'])
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
            
        if args.smoke_test and len(file_contents) > 3:
            print(f"  Too many files ({len(file_contents)}) for smoke test. Skipping to find a simpler issue.")
            continue

        print(f"  Processing {len(file_contents)} files...")
            
        # Generate Fix
        print("  Generating fix...")
        try:
            response = generate_fix_and_metadata(
                title, 
                issue['body'], 
                metadata['fix_prompt'], 
                file_contents
            )
            if not response:
                print("  Failed to get fix from LLM.")
                continue
                
            try:
                response_clean = response.replace("```json", "").replace("```", "").strip()
                fix_data = json.loads(response_clean)
            except json.JSONDecodeError as e:
                print(f"  JSON Decode Error: {e}")
                print(f"  Raw Response (first 500 chars): {response[:500]}...")
                continue
            
            # Create PR
            pr_number = create_pr(issue, fix_data, metadata)
            
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
