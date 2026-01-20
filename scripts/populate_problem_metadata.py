import json
import os
import sqlite3
import time
import urllib.error
import urllib.request

# Configuration
JSON_FILE = "problem_file_map.json"
DB_FILE = "problem_file_map.db"
API_KEY = os.environ.get("GEMINI_API_KEY")
STATE_FILE = "metadata_population_state.json"

# Category-specific severity criteria
SEVERITY_CRITERIA = {
    "Security": "Minimum Medium severity unless implications are minimal. High if exploitable or causes data exposure.",
    "Architecture": "High if requires major rewrite (>3 files), Medium if moderate refactoring, Low if minor adjustments.",
    "Performance": "High if causes >50% slowdown or resource exhaustion, Medium if 10-50% impact, Low if <10% impact.",
    "Code Quality": "High if causes crashes or silent failures, Medium if usability bugs, Low if annoyances.",
    "Operations": "High if causes crashes or silent failures, Medium if usability bugs, Low if annoyances.",
    "Compliance": "High if legal/regulatory violation, Medium if best practice, Low if optional improvement.",
}


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
                return None
        except urllib.error.HTTPError as e:
            if e.code == 429:  # Quota exceeded
                raise QuotaExceededException("API quota exceeded")
            continue
        except Exception:
            continue
    return None


class QuotaExceededException(Exception):
    pass


def get_severity_confidence(title, category, fix_prompt, file_count, proposed_count):
    """Use Gemini to assess severity and confidence."""
    criteria = SEVERITY_CRITERIA.get(category, "Assess based on impact and complexity.")

    prompt = f"""
Category: {category}
Problem: {title}
Fix Instructions: {fix_prompt}
Files Affected: {file_count} ({proposed_count} proposed new files)

Assess this problem's severity and your confidence in the assessment:
{criteria}

Return ONLY a JSON object:
{{
  "severity": "High|Medium|Low",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}
"""

    try:
        response = call_gemini(prompt)
        if response:
            # Clean markdown
            cleaned = response.replace("```json", "").replace("```", "").strip()
            result = json.loads(cleaned)
            return (
                result["severity"],
                float(result["confidence"]),
                result.get("reasoning", ""),
            )
    except QuotaExceededException:
        raise
    except Exception as e:
        print(f"  LLM parse error: {e}")

    return None, None, None


def heuristic_severity_confidence(category, proposed_count, file_count):
    """Fallback heuristics for severity and confidence."""
    # Severity heuristics
    severity_map = {
        "Security": "High",
        "Compliance": "High",
        "Architecture": "Medium",
        "Performance": "Medium",
        "Operations": "Medium",
        "Code Quality": "Low",
    }
    severity = severity_map.get(category, "Medium")

    # Confidence heuristics
    if proposed_count == 0:
        confidence = 0.8  # All existing files
    elif proposed_count == file_count:
        confidence = 0.4  # All proposed files
    else:
        confidence = 0.6  # Mixed

    return severity, confidence


def update_database_schema():
    """Add new columns to database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Check if columns exist
    cursor.execute("PRAGMA table_info(problems)")
    columns = [col[1] for col in cursor.fetchall()]

    if "severity" not in columns:
        cursor.execute("ALTER TABLE problems ADD COLUMN severity TEXT DEFAULT 'Medium'")
    if "confidence" not in columns:
        cursor.execute("ALTER TABLE problems ADD COLUMN confidence REAL DEFAULT 0.5")
    if "pr_created" not in columns:
        cursor.execute("ALTER TABLE problems ADD COLUMN pr_created INTEGER DEFAULT 0")
    if "pr_number" not in columns:
        cursor.execute("ALTER TABLE problems ADD COLUMN pr_number INTEGER DEFAULT NULL")

    conn.commit()
    conn.close()
    print("Database schema updated.")


def load_state():
    """Load processing state."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"processed_problems": [], "last_index": 0}


def save_state(state):
    """Save processing state."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def main():
    if not os.path.exists(JSON_FILE):
        print(f"Error: {JSON_FILE} not found!")
        return

    print("Updating database schema...")
    update_database_schema()

    print(f"Loading {JSON_FILE}...")
    with open(JSON_FILE, "r") as f:
        data = json.load(f)

    state = load_state()
    processed = set(state["processed_problems"])

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    problems = [
        (title, details) for title, details in data.items() if title not in processed
    ]
    total = len(problems)

    print(f"Processing {total} problems...")

    api_calls = 0
    for i, (title, details) in enumerate(problems):
        print(f"[{i+1}/{total}] {title}")

        category = details.get("category", "Unknown")
        fix_prompt = details.get("fix_prompt", "")
        resolved_files = details.get("resolved_files", [])

        file_count = len(resolved_files)
        proposed_count = sum(1 for f in resolved_files if "(Proposed)" in f)

        severity, confidence, reasoning = None, None, None

        # Try LLM first
        try:
            severity, confidence, reasoning = get_severity_confidence(
                title, category, fix_prompt, file_count, proposed_count
            )
            if severity and confidence:
                print(f"  LLM: {severity}, {confidence:.2f}")
                api_calls += 1
                time.sleep(1)  # Rate limit
        except QuotaExceededException:
            print("\n!!! API quota exceeded !!!")
            print("Checking quota reset time...")
            # For now, just halt - we'd need to check headers for reset time
            print("Halting process. Resume by running this script again.")
            save_state({"processed_problems": list(processed), "last_index": i})
            conn.close()
            return

        # Fallback to heuristics
        if not severity or not confidence:
            severity, confidence = heuristic_severity_confidence(
                category, proposed_count, file_count
            )
            print(f"  Heuristic: {severity}, {confidence:.2f}")

        # Update JSON
        details["severity"] = severity
        details["confidence"] = confidence
        details["pr_created"] = False
        details["pr_number"] = None

        # Update Database
        cursor.execute(
            """
            UPDATE problems
            SET severity = ?, confidence = ?, pr_created = 0, pr_number = NULL
            WHERE title = ?
        """,
            (severity, confidence, title),
        )

        processed.add(title)

        # Save state periodically
        if (i + 1) % 10 == 0:
            conn.commit()
            save_state({"processed_problems": list(processed), "last_index": i})

    conn.commit()
    conn.close()

    # Save updated JSON
    print(f"\nSaving updated {JSON_FILE}...")
    with open(JSON_FILE, "w") as f:
        json.dump(data, f, indent=2)

    # Clean up state file
    if os.path.exists(STATE_FILE):
        os.remove(STATE_FILE)

    print(f"\nCompleted! Made {api_calls} API calls.")


if __name__ == "__main__":
    main()
