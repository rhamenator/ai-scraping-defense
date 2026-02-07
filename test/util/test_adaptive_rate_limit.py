import unittest

from src.util import adaptive_rate_limit


class TestAdaptiveRateLimit(unittest.TestCase):
    def test_increase_limit(self):
        self.assertEqual(adaptive_rate_limit.compute_rate_limit([10, 20, 15], 60), 90)

    def test_decrease_limit(self):
        self.assertEqual(adaptive_rate_limit.compute_rate_limit([120, 130], 60), 30)

    def test_keep_base(self):
        self.assertEqual(adaptive_rate_limit.compute_rate_limit([50, 70], 60), 60)

    def test_empty_counts(self):
        self.assertEqual(adaptive_rate_limit.compute_rate_limit([], 60), 60)


if __name__ == "__main__":
    unittest.main()
