import json
import os
import sqlite3

# Configuration
JSON_FILE = "problem_file_map.json"
DB_FILE = "problem_file_map.db"


def create_database():
    """Create SQLite database and tables."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Create problems table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS problems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT UNIQUE NOT NULL,
            category TEXT,
            fix_prompt TEXT,
            original_affected TEXT
        )
    """
    )

    # Create problem_files table (one-to-many relationship)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS problem_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_title TEXT NOT NULL,
            file_path TEXT NOT NULL,
            is_proposed BOOLEAN NOT NULL DEFAULT 0,
            FOREIGN KEY (problem_title) REFERENCES problems(title)
        )
    """
    )

    # Create index for faster lookups
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_problem_files_title
        ON problem_files(problem_title)
    """
    )

    conn.commit()
    return conn


def load_json_to_db(json_file, conn):
    """Load problem_file_map.json into the database."""
    cursor = conn.cursor()

    # Load JSON
    print(f"Loading {json_file}...")
    with open(json_file, "r") as f:
        data = json.load(f)

    print(f"Found {len(data)} problems to import.")

    # Clear existing data
    cursor.execute("DELETE FROM problem_files")
    cursor.execute("DELETE FROM problems")

    # Insert data
    for title, details in data.items():
        category = details.get("category", "Unknown")
        fix_prompt = details.get("fix_prompt", "")
        original_affected = json.dumps(details.get("original_affected", []))
        resolved_files = details.get("resolved_files", [])

        # Insert problem
        cursor.execute(
            """
            INSERT INTO problems (title, category, fix_prompt, original_affected)
            VALUES (?, ?, ?, ?)
        """,
            (title, category, fix_prompt, original_affected),
        )

        # Insert resolved files
        for file_path in resolved_files:
            is_proposed = 1 if "(Proposed)" in file_path else 0
            # Clean the file path (remove the (Proposed) marker for storage)
            clean_path = file_path.replace(" (Proposed)", "").strip()

            cursor.execute(
                """
                INSERT INTO problem_files (problem_title, file_path, is_proposed)
                VALUES (?, ?, ?)
            """,
                (title, clean_path, is_proposed),
            )

    conn.commit()
    print(f"Imported {len(data)} problems into database.")


def print_statistics(conn):
    """Print database statistics."""
    cursor = conn.cursor()

    # Count problems
    cursor.execute("SELECT COUNT(*) FROM problems")
    problem_count = cursor.fetchone()[0]

    # Count total files
    cursor.execute("SELECT COUNT(*) FROM problem_files")
    file_count = cursor.fetchone()[0]

    # Count proposed files
    cursor.execute("SELECT COUNT(*) FROM problem_files WHERE is_proposed = 1")
    proposed_count = cursor.fetchone()[0]

    # Count by category
    cursor.execute(
        """
        SELECT category, COUNT(*)
        FROM problems
        GROUP BY category
        ORDER BY COUNT(*) DESC
    """
    )
    categories = cursor.fetchall()

    print("\nDatabase Statistics:")
    print(f"  Total Problems: {problem_count}")
    print(f"  Total Files: {file_count}")
    print(f"  Proposed Files: {proposed_count}")
    print(f"  Existing Files: {file_count - proposed_count}")

    print("\nProblems by Category:")
    for category, count in categories:
        print(f"  {category}: {count}")


def sample_queries(conn):
    """Run some sample queries to demonstrate usage."""
    cursor = conn.cursor()

    print("\nSample Query: Problems affecting 'src/shared/authz.py'")
    cursor.execute(
        """
        SELECT DISTINCT p.title, p.category
        FROM problems p
        JOIN problem_files pf ON p.title = pf.problem_title
        WHERE pf.file_path = 'src/shared/authz.py'
        LIMIT 5
    """
    )

    for row in cursor.fetchall():
        print(f"  - {row[0]} ({row[1]})")

    print("\nSample Query: Problems requiring new files")
    cursor.execute(
        """
        SELECT p.title, COUNT(pf.id) as proposed_count
        FROM problems p
        JOIN problem_files pf ON p.title = pf.problem_title
        WHERE pf.is_proposed = 1
        GROUP BY p.title
        ORDER BY proposed_count DESC
        LIMIT 5
    """
    )

    for row in cursor.fetchall():
        print(f"  - {row[0]}: {row[1]} proposed files")


def main():
    if not os.path.exists(JSON_FILE):
        print(f"Error: {JSON_FILE} not found!")
        return

    print(f"Creating database: {DB_FILE}")
    conn = create_database()

    load_json_to_db(JSON_FILE, conn)
    print_statistics(conn)
    sample_queries(conn)

    conn.close()
    print(f"\nDatabase saved to: {DB_FILE}")
    print(f"   You can query it using: sqlite3 {DB_FILE}")


if __name__ == "__main__":
    main()
