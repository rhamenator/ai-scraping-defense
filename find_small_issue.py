import json

with open('problem_file_map.json', 'r') as f:
    data = json.load(f)

for title, info in data.items():
    resolved = info.get('resolved_files', [])
    if not info.get('pr_created') and 0 < len(resolved) <= 3:
        print(f"Found issue: {title}")
        print(f"Files: {len(resolved)}")
        # Also print the files to be sure
        print(f"Resolved Files: {resolved}")
        break
