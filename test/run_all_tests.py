# test/run_all_tests.py
import unittest
import os
import sys


def main():
    """Discovers and runs all tests in the project."""
    # Get the project root directory (the parent of the 'test' directory)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # Add the project root, 'src', and 'test' directories to the path so imports
    # like 'from tarpit import markov_generator' or 'from src.admin_ui' work and
    # test packages can be imported correctly.
    src_path = os.path.join(project_root, "src")
    test_path = os.path.join(project_root, "test")

    # Insert in order of precedence: tests first so they override modules with
    # the same name in src or project root, then src, then the project root.
    for path in [test_path, src_path, project_root]:
        if path not in sys.path:
            sys.path.insert(0, path)

    print(f"Project root added to path: {project_root}")
    print("Discovering tests...")
    print("-" * 70)

    # Use the unittest TestLoader to discover all tests
    loader = unittest.TestLoader()
    suite = loader.discover(
        start_dir=test_path,
        pattern="test_*.py",
        top_level_dir=project_root,
    )

    # Use a TextTestRunner to run the suite
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("-" * 70)

    # Exit with a non-zero status code if any tests failed, for CI/CD integration
    if not result.wasSuccessful():
        print("Test suite failed.")
        sys.exit(1)
    else:
        print("Test suite passed successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()
