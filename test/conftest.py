import os
import shutil
import tempfile

import pytest

# Set up test environment variables before importing any application code
# This must be done before importing any src modules that create directories at import time
os.environ.setdefault("SYSTEM_SEED", "test_seed")

# The shared apps (admin UI and others) are module-level singletons created at import time, and their request rate
# limiter keeps one bucket per client for the whole test process. The suite sends far more than the default 100 requests
# a minute from the same test client, so tests would fail with 429 depending on how fast the machine runs them. Make
# the limit practically unlimited for the suite (the setting must be a positive integer); tests that exercise rate
# limiting build their own app with an explicit RATE_LIMIT_REQUESTS.
os.environ.setdefault("RATE_LIMIT_REQUESTS", "1000000")

# Use temp directory for logs and data in tests to avoid permission issues
# Create a unique subdirectory to avoid conflicts with other test runs
temp_base = tempfile.gettempdir()
unique_test_dir = os.path.join(temp_base, f"ai-scraping-defense-tests-{os.getpid()}")
test_data_dir = os.path.join(unique_test_dir, "data")
test_logs_dir = os.path.join(unique_test_dir, "logs")

# Create test directories
os.makedirs(test_data_dir, exist_ok=True)
os.makedirs(test_logs_dir, exist_ok=True)

# Set environment variables for all log files and data paths
os.environ.setdefault("LOG_DIR", test_logs_dir)
os.environ.setdefault("AUDIT_LOG_FILE", os.path.join(test_logs_dir, "test_audit.log"))
os.environ.setdefault(
    "HONEYPOT_LOG_FILE", os.path.join(test_logs_dir, "test_honeypot.log")
)
os.environ.setdefault(
    "BLOCK_LOG_FILE", os.path.join(test_logs_dir, "test_block_events.log")
)
os.environ.setdefault(
    "CAPTCHA_SUCCESS_LOG", os.path.join(test_logs_dir, "test_captcha_success.log")
)
os.environ.setdefault(
    "DECISIONS_DB_PATH", os.path.join(test_data_dir, "test_decisions.db")
)
os.environ.setdefault(
    "SECURITY_EVENTS_DB_PATH", os.path.join(test_data_dir, "security_events.db")
)
os.environ.setdefault("SURICATA_EVE_LOG", os.path.join(test_logs_dir, "test_eve.json"))


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_dirs():
    """Clean up temporary test directories after all tests complete."""
    yield
    # Cleanup after all tests complete
    if os.path.exists(unique_test_dir):
        shutil.rmtree(unique_test_dir, ignore_errors=True)
