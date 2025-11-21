import os
import tempfile

# Set up test environment variables before importing any application code
# This must be done before importing any src modules that create directories at import time
os.environ.setdefault("SYSTEM_SEED", "test_seed")

# Use temp directory for logs and data in tests to avoid permission issues
temp_dir = tempfile.gettempdir()
test_data_dir = os.path.join(temp_dir, "test_data")
test_logs_dir = os.path.join(temp_dir, "test_logs")

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
os.environ.setdefault("SURICATA_EVE_LOG", os.path.join(test_logs_dir, "test_eve.json"))
