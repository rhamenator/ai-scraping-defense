# test\metrics.test.py
import unittest
from metrics import MetricsCollector

class TestMetricsCollector(unittest.TestCase):

    def setUp(self):
        self.collector = MetricsCollector()

    def test_increment_counter(self):
        self.collector.increment("requests")
        self.assertEqual(self.collector.get("requests"), 1)
        self.collector.increment("requests")
        self.assertEqual(self.collector.get("requests"), 2)

    def test_set_and_get_metric(self):
        self.collector.set("uptime", 123)
        self.assertEqual(self.collector.get("uptime"), 123)

    def test_get_unknown_metric_returns_zero(self):
        self.assertEqual(self.collector.get("unknown"), 0)

    def test_reset_metrics(self):
        self.collector.set("errors", 5)
        self.collector.reset()
        self.assertEqual(self.collector.get("errors"), 0)

if __name__ == '__main__':
    unittest.main()
