# test\run_all_tests.py
import unittest
import os
import sys

# Ensure test modules can import the source files correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def discover_and_run_tests():
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=os.path.dirname(__file__), pattern='*.test.py')
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)

if __name__ == '__main__':
    discover_and_run_tests()
