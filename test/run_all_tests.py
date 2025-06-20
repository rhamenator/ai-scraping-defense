# test/run_all_tests.py
import unittest
import os
import sys

def run_all_tests():
    """
    Discovers and runs all tests in the 'test' directory and its subdirectories.
    This script should be run from the root of the project.
    e.g., python -m test.run_all_tests
    """
    # Add the project root to the Python path to allow absolute imports of source modules
    # e.g., from shared import config
    project_root = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    print(f"Project root added to path: {project_root}")
    print("-" * 70)
    
    # Use the test loader to discover all tests
    # The start directory is the 'test' directory where this script resides.
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=os.path.dirname(__file__), pattern='*.test.py')
    
    # Use a text test runner to execute the suite
    runner = unittest.TextTestRunner(verbosity=2, failfast=False)
    
    print(f"Running test suite...")
    print("-" * 70)
    
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
    run_all_tests()
