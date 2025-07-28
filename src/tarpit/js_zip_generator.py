# tarpit/js_zip_generator.py
# Generates a ZIP archive containing fake JavaScript files for honeypot purposes.

import zipfile
import os
import random
import string
import datetime
import logging

logger = logging.getLogger(__name__)

try:
    from jszip_rs import generate_realistic_filename as rs_generate_filename
    from jszip_rs import create_fake_js_zip as rs_create_zip

    RUST_ENABLED = True
    logger.info("jszip_rs module loaded; using Rust implementation where possible.")
except Exception as e:
    RUST_ENABLED = False
    logger.warning(
        f"Could not import jszip_rs: {e}. Falling back to Python implementation."
    )

# --- Configuration ---
DEFAULT_ARCHIVE_DIR = (
    "/app/fake_archives"  # Should match volume mount in docker-compose
)
NUM_FAKE_FILES = 15
MIN_FILE_SIZE_KB = 5
MAX_FILE_SIZE_KB = 50
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"

# Realistic-sounding but ultimately fake JS filenames
FILENAME_PREFIXES = [
    "analytics_bundle",
    "vendor_lib",
    "core_framework",
    "ui_component_pack",
    "polyfills_es6",
    "runtime_utils",
    "shared_modules",
    "feature_flags_data",
    "config_loader",
    "auth_client_sdk",
    "graph_rendering_engine",
    "data_sync_worker",
]
FILENAME_SUFFIXES = ["_min", "_pack", "_bundle", "_lib", "_core", ""]
FILENAME_EXT = ".js"

# --- Helper Functions ---


def generate_random_string(length):
    """Generates a random string of printable ASCII characters."""
    # Include spaces and punctuation for more realistic "junk" content
    chars = (
        string.ascii_letters + string.digits + string.punctuation + " " * 10
    )  # Weight spaces
    return "".join(random.choice(chars) for _ in range(length))


def generate_realistic_filename():
    """Generates a somewhat plausible JS filename."""
    if RUST_ENABLED:
        try:
            return rs_generate_filename()
        except Exception as e:
            logger.warning(
                f"jszip_rs error generating filename: {e}; using Python fallback"
            )
    prefix = random.choice(FILENAME_PREFIXES)
    suffix = random.choice(FILENAME_SUFFIXES)
    random_hash = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}{suffix}.{random_hash}{FILENAME_EXT}"


def create_fake_js_zip(
    output_dir=DEFAULT_ARCHIVE_DIR,
    num_files=NUM_FAKE_FILES,
    recursive_depth: int = 0,
):
    """Creates a ZIP archive with fake JS files. If ``recursive_depth`` is
    greater than 0, an additional nested archive is added inside."""
    if RUST_ENABLED:
        try:
            return rs_create_zip(output_dir, num_files)
        except Exception as e:
            logger.warning(
                f"jszip_rs error creating archive: {e}; falling back to Python implementation"
            )
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create output directory {output_dir}: {e}")
        return None

    timestamp = datetime.datetime.now().strftime(TIMESTAMP_FORMAT)
    zip_filename = os.path.join(output_dir, f"assets_{timestamp}.zip")

    logger.info(f"Creating fake JS archive: {zip_filename}")

    try:
        with zipfile.ZipFile(zip_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
            for i in range(num_files):
                fake_filename = generate_realistic_filename()
                file_size_bytes = random.randint(
                    MIN_FILE_SIZE_KB * 1024, MAX_FILE_SIZE_KB * 1024
                )

                # Generate somewhat plausible JS-like junk content
                content = f"// Fake module: {fake_filename}\n"
                content += f"// Generated: {datetime.datetime.now().isoformat()}\n\n"
                content += "(function() {\n"
                # Add some pseudo-random variables and functions
                num_vars = random.randint(5, 20)
                for _ in range(num_vars):
                    var_name = "".join(
                        random.choices(string.ascii_lowercase, k=random.randint(4, 10))
                    )
                    var_value = random.choice(
                        [
                            "null",
                            "true",
                            "false",
                            "[]",
                            "{}",
                            f'"{generate_random_string(random.randint(10, 30))}"',
                            str(random.randint(0, 1000)),
                        ]
                    )
                    content += f"  var {var_name} = {var_value};\n"

                num_funcs = random.randint(2, 8)
                for _ in range(num_funcs):
                    func_name = "".join(
                        random.choices(string.ascii_lowercase, k=random.randint(6, 15))
                    )
                    content += f"  function {func_name}() {{ /* {generate_random_string(random.randint(50, 150))} */ return {random.choice(['null', 'true', 'false'])}; }}\n"

                # Fill remaining size with random comments/strings to approximate size
                current_size = len(content.encode("utf-8"))
                remaining_size = file_size_bytes - current_size
                if remaining_size > 0:
                    # Add large multi-line comments
                    content += (
                        "\n/*\n"
                        + generate_random_string(remaining_size - 10)
                        + "\n*/\n"
                    )  # Adjust padding as needed

                content += "\n})();\n"

                # Add file to zip
                zipf.writestr(fake_filename, content)

            if recursive_depth > 0:
                nested_name = "nested_" + generate_realistic_filename().replace(
                    ".js", ".zip"
                )
                nested_path = create_fake_js_zip(
                    output_dir=output_dir,
                    num_files=max(1, num_files // 2),
                    recursive_depth=recursive_depth - 1,
                )
                if nested_path:
                    with open(nested_path, "rb") as nf:
                        zipf.writestr(nested_name, nf.read())

        logger.info(
            f"Successfully created {zip_filename} with {num_files} fake files."
        )
        return zip_filename

    except Exception as e:
        logger.error(f"Failed to create zip file {zip_filename}: {e}")
        # Clean up partially created file if error occurs
        if os.path.exists(zip_filename):
            try:
                os.remove(zip_filename)
            except OSError:
                pass
        return None


# Example Usage (if run directly)
if __name__ == "__main__":
    created_file = create_fake_js_zip()
    if created_file:
        print(f"Test archive created at: {created_file}")
    else:
        print("Test archive creation failed.")
