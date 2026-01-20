import json
import sqlite3

# Query database
conn = sqlite3.connect("problem_file_map.db")
c = conn.cursor()

print("=== SEVERITY DISTRIBUTION ===")
for row in c.execute("SELECT severity, COUNT(*) FROM problems GROUP BY severity"):
    print(f"  {row[0]}: {row[1]}")

print("\n=== CONFIDENCE STATS ===")
stats = c.execute(
    "SELECT AVG(confidence), MIN(confidence), MAX(confidence) FROM problems"
).fetchone()
print(f"  Average: {stats[0]:.3f}")
print(f"  Min: {stats[1]}")
print(f"  Max: {stats[2]}")

print("\n=== SAMPLE PROBLEMS ===")
for row in c.execute(
    "SELECT title, category, severity, ROUND(confidence, 2) FROM problems LIMIT 10"
):
    print(f"  {row[0][:50]:50} | {row[1]:12} | {row[2]:6} | {row[3]}")

print("\n=== PR TRACKING FIELDS ===")
created_count = c.execute(
    "SELECT COUNT(*) FROM problems WHERE pr_created = 1"
).fetchone()[0]
print(f"  PRs Created: {created_count}/695")

conn.close()

# Verify JSON
print("\n=== JSON VERIFICATION ===")
with open("problem_file_map.json", "r") as f:
    data = json.load(f)
first_problem = list(data.values())[0]
print("  Sample Problem Fields:")
for key in ["severity", "confidence", "pr_created", "pr_number"]:
    print(f"    {key}: {first_problem.get(key, 'MISSING')}")
