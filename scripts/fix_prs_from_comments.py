import json
import os
import subprocess
import time
import argparse
import urllib.request
import urllib.error

# Configuration
API_KEY = os.environ.get("GEMINI_API_KEY")

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

def fetch_open_prs(limit=100):
    print(f"Fetching open PRs (limit {limit})...")
    cmd = [
        "gh", "pr", "list", 
        "--state", "open", 
        "--label", "automated-pr",
        "--json", "number,title,headRefName,url", 
        "--limit", str(limit)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Failed to fetch PRs: {e}")
        return []

def fetch_pr_comments(pr_number):
    cmd = [
        "gh", "pr", "view", str(pr_number),
        "--json", "comments,reviews"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        comments = []
        # Collect regular comments
        for c in data.get('comments', []):
            if c['author']['login'] == 'copilot-pull-request-reviewer':
                comments.append(c['body'])
                
        # Collect reviews
        for r in data.get('reviews', []):
            if r['author']['login'] == 'copilot-pull-request-reviewer':
                comments.append(r['body'])
                
        return comments
    except subprocess.CalledProcessError as e:
        print(f"Failed to fetch comments for PR #{pr_number}: {e}")
        return []

def get_changed_files(pr_number):
    cmd = ["gh", "pr", "view", str(pr_number), "--json", "files"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return [f['path'] for f in data.get('files', [])]
    except:
        return []

def generate_fix_from_comments(title, comments, file_contents):
    prompt = f"""
You are an expert secure code fixing assistant.
I have a Pull Request that has received feedback from an automated code reviewer (Copilot).
Your task is to update the code to address the reviewer's comments.

PR Title: {title}

Reviewer Comments:
{json.dumps(comments, indent=2)}

Current File Contents:
"""
    for path, content in file_contents.items():
        prompt += f"\n--- START FILE: {path} ---\n{content}\n--- END FILE: {path} ---\n"

    prompt += """
Output Format:
Please provide the response in strict JSON format as follows:
{
    "explanation": "Brief explanation of how you addressed the comments...",
    "files": {
        "path/to/file1": "Full updated content of file1...",
        "path/to/file2": "Full updated content of file2..."
    }
}
Do not include markdown formatting (```json) in the response, just the raw JSON string.
Ensure the JSON is valid and properly escaped.
"""
    return call_gemini(prompt)

def apply_fix_and_push(pr, fix_data):
    pr_number = pr['number']
    branch_name = pr['headRefName']
    
    print(f"Applying fix to PR #{pr_number} on branch {branch_name}...")
    
    # Capture current branch
    try:
        original_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
    except:
        original_branch = "main"

    try:
        # Checkout PR branch
        subprocess.run(["git", "fetch", "origin", branch_name], check=True)
        subprocess.run(["git", "checkout", branch_name], check=True)
        # Pull latest to be sure
        subprocess.run(["git", "pull", "origin", branch_name], check=False)
        
        files_changed = []
        for path, new_content in fix_data["files"].items():
            try:
                # Ensure dir exists
                if os.path.dirname(path):
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                subprocess.run(["git", "add", path], check=True)
                files_changed.append(path)
            except Exception as e:
                print(f"Failed to write {path}: {e}")
                
        if not files_changed:
            print("No files changed. Skipping push.")
            return
            
        # Commit
        subprocess.run(["git", "commit", "-m", f"Refactor: Address Copilot comments for PR #{pr_number}"], check=True)
        
        # Push
        subprocess.run(["git", "push", "origin", branch_name], check=True)
        
        # Add label
        subprocess.run(["gh", "pr", "edit", str(pr_number), "--add-label", "auto-fixed"], check=False)
        
        print(f"Successfully updated PR #{pr_number}")
        
    except Exception as e:
        print(f"Error applying fix: {e}")
    finally:
        print(f"Returning to branch: {original_branch}")
        subprocess.run(["git", "checkout", original_branch], check=False)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr-number", type=int, help="Target specific PR number")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    
    if args.pr_number:
        # Fetch specific PR
        # We can mock the list format
        try:
            cmd = ["gh", "pr", "view", str(args.pr_number), "--json", "number,title,headRefName,url"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            prs = [json.loads(result.stdout)]
        except Exception as e:
            print(f"Failed to fetch PR #{args.pr_number}: {e}")
            return
    else:
        prs = fetch_open_prs(limit=args.limit)
        
    print(f"Found {len(prs)} PRs to check.")
    
    for pr in prs:
        pr_number = pr['number']
        print(f"\nChecking PR #{pr_number}: {pr['title']}")
        
        comments = fetch_pr_comments(pr_number)
        if not comments:
            print("  No Copilot comments found. Skipping.")
            continue
            
        print(f"  Found {len(comments)} Copilot comments/reviews.")
        
        # Get file contents
        changed_files = get_changed_files(pr_number)
        file_contents = {}
        for path in changed_files:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    file_contents[path] = f.read()
            else:
                # Maybe it's a new file not in current branch? 
                # We should probably checkout the PR branch first to read files?
                # Or use `gh pr view` to get content?
                # Simpler: assume we have the file locally or can read it after checkout.
                # Actually, to read the *current* state of the PR, we MUST checkout the branch or use `gh` to fetch content.
                # Let's use `gh api` or just checkout the branch briefly to read.
                pass
        
        # Better approach: Checkout branch to read files
        try:
            original_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
            subprocess.run(["git", "fetch", "origin", pr['headRefName']], check=True, capture_output=True)
            subprocess.run(["git", "checkout", pr['headRefName']], check=True, capture_output=True)
            
            for path in changed_files:
                if os.path.exists(path):
                    with open(path, 'r', encoding='utf-8') as f:
                        file_contents[path] = f.read()
                        
            subprocess.run(["git", "checkout", original_branch], check=True, capture_output=True)
        except Exception as e:
            print(f"  Error reading files from branch: {e}")
            subprocess.run(["git", "checkout", "main"], check=False) # Fallback
            continue

        if not file_contents:
            print("  No file contents read. Skipping.")
            continue
            
        print("  Generating fix from comments...")
        try:
            response = generate_fix_from_comments(pr['title'], comments, file_contents)
            if not response:
                print("  Failed to get response from Gemini.")
                continue
                
            try:
                response_clean = response.replace("```json", "").replace("```", "").strip()
                fix_data = json.loads(response_clean)
            except json.JSONDecodeError:
                print("  JSON Decode Error from Gemini.")
                continue
                
            apply_fix_and_push(pr, fix_data)
            
        except Exception as e:
            print(f"  Error processing PR: {e}")

if __name__ == "__main__":
    main()
