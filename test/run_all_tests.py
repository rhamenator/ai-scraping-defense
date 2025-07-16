# test/run_all_tests.py
import unittest
import os
import sys

def main():
    """Discovers and runs all tests in the project."""
    # Get the project root directory (the parent of the 'test' directory)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    
    # Add the project root and 'src' directory to the path so imports like
    # 'from tarpit import markov_generator' or 'from src.admin_ui' work.
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    src_path = os.path.join(project_root, 'src')
    if src_path not in sys.path:
        # Append rather than prepend so that test packages like 'admin_ui'
        # in the test directory take precedence over the actual code packages
        # during discovery.
        sys.path.append(src_path)

    print(f"Project root added to path: {project_root}")
    print("Discovering tests...")
    print("-" * 70)
    
    # Use the unittest TestLoader to discover all tests
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir='test', pattern='test_*.py')

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

if __name__ == '__main__':
    main()