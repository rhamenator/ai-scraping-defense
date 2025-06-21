# tarpit/rotating_archive.py
# Periodically generates new fake JS ZIP archives and removes old ones.

import os
import glob
import time
import schedule # Using 'schedule' library for easy job scheduling
import sys

# --- Import the generator script ---
try:
    from js_zip_generator import create_fake_js_zip, DEFAULT_ARCHIVE_DIR
except ImportError:
    print("ERROR: Could not import create_fake_js_zip from js_zip_generator.py. Ensure it's in the same directory or PYTHONPATH.")
    sys.exit(1)

# --- Configuration ---
ARCHIVE_DIR = DEFAULT_ARCHIVE_DIR
ARCHIVE_PATTERN = os.path.join(ARCHIVE_DIR, "assets_*.zip")
MAX_ARCHIVES_TO_KEEP = 5  # Keep the latest N archives
GENERATION_INTERVAL_MINUTES = 60 # Generate a new archive every hour

def rotate_archives():
    """Generates a new archive and cleans up old ones."""
    print(f"Running archive rotation task at {time.strftime('%Y-%m-%d %H:%M:%S')}...")

    # 1. Generate a new archive
    new_archive = create_fake_js_zip(output_dir=ARCHIVE_DIR)
    if not new_archive:
        print("Archive generation failed. Skipping cleanup.")
        return

    # 2. Get list of existing archives, sorted by modification time (newest first)
    try:
        existing_archives = sorted(
            glob.glob(ARCHIVE_PATTERN),
            key=os.path.getmtime,
            reverse=True
        )
    except Exception as e:
        print(f"ERROR: Failed to list existing archives in {ARCHIVE_DIR}: {e}")
        return

    # 3. Determine archives to delete
    archives_to_delete = existing_archives[MAX_ARCHIVES_TO_KEEP:]

    # 4. Delete old archives
    if archives_to_delete:
        print(f"Found {len(existing_archives)} archives. Keeping {MAX_ARCHIVES_TO_KEEP}, deleting {len(archives_to_delete)}.")
        for old_archive in archives_to_delete:
            try:
                os.remove(old_archive)
                print(f"  Deleted old archive: {old_archive}")
            except OSError as e:
                print(f"ERROR: Failed to delete old archive {old_archive}: {e}")
    else:
        print(f"Found {len(existing_archives)} archives. No old archives to delete.")

    print("Archive rotation task finished.")


# --- Main Execution Logic ---
if __name__ == "__main__":
    print("--- Rotating Archive Scheduler ---")
    print(f"Watching directory: {ARCHIVE_DIR}")
    print(f"Keeping latest: {MAX_ARCHIVES_TO_KEEP} archives")
    print(f"Generating new archive every: {GENERATION_INTERVAL_MINUTES} minutes")
    print("---------------------------------")

    # Schedule the job
    schedule.every(GENERATION_INTERVAL_MINUTES).minutes.do(rotate_archives)

    # Run the first rotation immediately
    print("Running initial rotation...")
    rotate_archives()

    # Keep the script running to execute scheduled jobs
    print(f"Scheduler started. Next run in approx {GENERATION_INTERVAL_MINUTES} minutes.")
    while True:
        schedule.run_pending()
        time.sleep(60) # Check every minute