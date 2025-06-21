# test/run_all_tests.py
import unittest
import os
import sys

def main():
    """Discovers and runs all tests in the project."""
    # Get the project root directory (the parent of the 'test' directory)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    
    # Define the path to the source code directory
    src_path = os.path.join(project_root, 'src')

    # Add the src directory to the Python path.
    # This is crucial so that tests can import modules like 'from admin_ui import ...'
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    print(f"Source root added to path: {src_path}")
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
