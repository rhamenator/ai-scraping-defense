import json
import os
import subprocess
import time
import urllib.error
import urllib.request

# Configuration
PROBLEMS_DIR = "."
OUTPUT_FILE = "problem_file_map.json"
API_KEY = os.environ.get("GEMINI_API_KEY")


def call_gemini(prompt):
    """Calls Gemini API to generate content."""
    if not API_KEY:
        return None

    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}

    models = ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-flash-latest"]

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
        except Exception as e:
            print(f"  Model {model} failed: {e}")
            continue
    return None


def get_all_files():
    """Returns a list of all files in the git repository."""
    try:
        result = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
        return [f.strip() for f in result.stdout.splitlines() if f.strip()]
    except Exception as e:
        print(f"Error getting file list: {e}")
        return []


def load_problems():
    """Loads all problems from JSON files."""
    problems = []
    for filename in os.listdir(PROBLEMS_DIR):
        if (
            filename.endswith(".json")
            and "problems" in filename
            and filename != OUTPUT_FILE
        ):
            try:
                with open(filename, "r") as f:
                    data = json.load(f)
                    for key, val in data.items():
                        if isinstance(val, dict) and "problems" in val:
                            category = val.get("category", key)
                            for p in val["problems"]:
                                p["_source_file"] = filename
                                p["_category"] = category
                                problems.append(p)
            except Exception as e:
                print(f"Error loading {filename}: {e}")
    return problems


def infer_files(title, description, affected_desc, file_list):
    """Uses LLM to infer files from abstract description."""
    # Chunk file list if too large (naive truncation for now)
    files_str = "\n".join(file_list[:2000])

    prompt = f"""
I have a software project with the following files (subset):
{files_str}

I have a problem reported:
Title: "{title}"
Description: "{description}"
Affected Component/File Description: "{affected_desc}"

The "Affected Component" is abstract. I need to map this to specific source code files.
1. If existing files in the project list are relevant, list them.
2. If this requires creating NEW files (e.g. missing feature), propose standard file paths.

Based on the problem and the file list, which specific files are most likely affected or need to be created?
Return ONLY a JSON list of file paths. Example: ["src/auth.py", "config/security.yaml"]
If you cannot determine any with confidence, return [].
"""
    print("  -> Calling Gemini...")
    response = call_gemini(prompt)
    if response:
        # print(f"  -> Raw response: {response[:100]}...")
        try:
            # Clean markdown
            cleaned = response.replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned)
        except Exception as e:
            print(f"  -> JSON Parse Error: {e}")
            pass
    else:
        print("  -> No response from Gemini.")
    return []


def main():
    print("Indexing files...")
    all_files = get_all_files()
    print(f"Found {len(all_files)} files in repository.")

    print("Loading problems...")
    problems = load_problems()
    print(f"Loaded {len(problems)} problems.")

    problem_map = {}

    for i, p in enumerate(problems):
        title = p.get("problem") or p.get("message")
        if not title:
            continue

        description = p.get("description", "")
        raw_affected = p.get("affected_files", [])
        if isinstance(raw_affected, str):
            raw_affected = [raw_affected]

        resolved_files = []
        needs_inference = False
        affected_desc_for_inference = []

        for affected in raw_affected:
            # 1. Exact Match
            if affected in all_files:
                resolved_files.append(affected)
                continue

            # 2. Fuzzy Match (Substring)
            # Be careful with short strings.
            if len(affected) > 5:
                matches = [f for f in all_files if affected in f]
                if len(matches) == 1:
                    resolved_files.append(matches[0])
                    continue
                elif len(matches) > 1:
                    # Ambiguous, maybe add all? Or treat as needing inference?
                    # Let's add all for now if it's a reasonable number
                    if len(matches) < 5:
                        resolved_files.extend(matches)
                        continue

            # 3. Path normalization (e.g. ./file vs file)
            norm = affected.lstrip("./").lstrip("/")
            if norm in all_files:
                resolved_files.append(norm)
                continue

            # If we get here, it's likely abstract or missing
            needs_inference = True
            affected_desc_for_inference.append(affected)

        if needs_inference:
            print(f"[{i+1}/{len(problems)}] Inferring files for: {title}")
            inferred = infer_files(
                title, description, ", ".join(affected_desc_for_inference), all_files
            )
            if inferred:
                print(f"  -> Inferred: {inferred}")
                for f in inferred:
                    if f in all_files:
                        resolved_files.append(f)
                    else:
                        # Mark as proposed new file
                        resolved_files.append(f"{f} (Proposed)")
            else:
                print("  -> Inference failed.")
            time.sleep(1)  # Rate limit

        # Deduplicate
        resolved_files = list(set(resolved_files))

        problem_map[title] = {
            "original_affected": raw_affected,
            "resolved_files": resolved_files,
            "category": p.get("_category"),
            "fix_prompt": p.get("fix_prompt"),
        }

    print(f"Saving map to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, "w") as f:
        json.dump(problem_map, f, indent=2)
    print("Done.")


if __name__ == "__main__":
    main()
