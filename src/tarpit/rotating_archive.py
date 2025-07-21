# tarpit/rotating_archive.py
# Periodically generates new fake JS ZIP archives and removes old ones.

import os
import glob
import time
import schedule  # Using 'schedule' library for easy job scheduling
import sys
import logging

# Configure module-level logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Import the generator script ---
try:
    from .js_zip_generator import create_fake_js_zip, DEFAULT_ARCHIVE_DIR
except ImportError as e:
    # Raise a clearer error so importing modules (like tests) fail gracefully
    raise ImportError(
        "js_zip_generator.py is required for rotating_archive but could not be found"
    ) from e

# --- Configuration ---
ARCHIVE_DIR = DEFAULT_ARCHIVE_DIR
ARCHIVE_PATTERN = os.path.join(ARCHIVE_DIR, "assets_*.zip")
MAX_ARCHIVES_TO_KEEP = 5  # Keep the latest N archives
GENERATION_INTERVAL_MINUTES = 60  # Generate a new archive every hour


def rotate_archives():
    """Generates a new archive and cleans up old ones."""
    logger.info(
        f"Running archive rotation task at {time.strftime('%Y-%m-%d %H:%M:%S')}..."
    )

    # 1. Generate a new archive
    new_archive = create_fake_js_zip(output_dir=ARCHIVE_DIR)
    if not new_archive:
        logger.error("Archive generation failed. Skipping cleanup.")
        return

    # 2. Get list of existing archives, sorted by modification time (newest first)
    try:
        existing_archives = sorted(
            glob.glob(ARCHIVE_PATTERN), key=os.path.getmtime, reverse=True
        )
    except Exception as e:
        logger.error(f"Failed to list existing archives in {ARCHIVE_DIR}: {e}")
        return

    # 3. Determine archives to delete
    archives_to_delete = existing_archives[MAX_ARCHIVES_TO_KEEP:]

    # 4. Delete old archives
    if archives_to_delete:
        logger.info(
            f"Found {len(existing_archives)} archives. Keeping {MAX_ARCHIVES_TO_KEEP}, deleting {len(archives_to_delete)}."
        )
        for old_archive in archives_to_delete:
            try:
                os.remove(old_archive)
                logger.info(f"  Deleted old archive: {old_archive}")
            except OSError as e:
                logger.error(f"Failed to delete old archive {old_archive}: {e}")
    else:
        logger.info(
            f"Found {len(existing_archives)} archives. No old archives to delete."
        )

    logger.info("Archive rotation task finished.")


# --- Main Execution Logic ---
if __name__ == "__main__":
    logger.info("--- Rotating Archive Scheduler ---")
    logger.info(f"Watching directory: {ARCHIVE_DIR}")
    logger.info(f"Keeping latest: {MAX_ARCHIVES_TO_KEEP} archives")
    logger.info(f"Generating new archive every: {GENERATION_INTERVAL_MINUTES} minutes")
    logger.info("---------------------------------")

    # Schedule the job
    schedule.every(GENERATION_INTERVAL_MINUTES).minutes.do(rotate_archives)

    # Run the first rotation immediately
    logger.info("Running initial rotation...")
    rotate_archives()

    # Keep the script running to execute scheduled jobs
    logger.info(
        f"Scheduler started. Next run in approx {GENERATION_INTERVAL_MINUTES} minutes."
    )
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute
