# test/shared/metrics.test.py
import unittest
from unittest.mock import patch
from prometheus_client import CollectorRegistry, generate_latest
from src.shared import metrics
import importlib

class TestMetricsComprehensive(unittest.TestCase):

    def setUp(self):
        """
        Create a new registry for each test to ensure isolation.
        We will patch the REGISTRY object in the metrics module.
        """
        self.registry = CollectorRegistry()
        self.registry_patcher = patch('src.shared.metrics.REGISTRY', self.registry)
        self.registry_patcher.start()
        # Reload the module to redefine metrics on our new patched registry
        importlib.reload(metrics)

    def tearDown(self):
        """Stop the patch to clean up."""
        self.registry_patcher.stop()
        # Restore the original module state
        importlib.reload(metrics)

    def test_increment_counter_metric(self):
        """Test the counter helper function with and without labels."""
        # Test counter without labels
        counter_no_labels = metrics.TARPIT_ENTRIES
        metrics.increment_counter_metric(counter_no_labels)
        metrics.increment_counter_metric(counter_no_labels)
        self.assertEqual(self.registry.get_sample_value(f'{counter_no_labels._name}_total'), 2.0)

        # Test counter with labels
        counter_with_labels = metrics.REQUEST_COUNT
        labels = {'method': 'GET', 'endpoint': '/api', 'status_code': '200'}
        metrics.increment_counter_metric(counter_with_labels, labels=labels)
        self.assertEqual(self.registry.get_sample_value(f'{counter_with_labels._name}_total', labels), 1.0)

    def test_set_gauge_metric(self):
        """Test the gauge set helper function with and without labels."""
        # Replaced undefined metric with 'ACTIVE_USERS' which is defined in metrics.py
        gauge_no_labels = metrics.ACTIVE_USERS
        metrics.set_gauge_metric(gauge_no_labels, 123)
        self.assertEqual(self.registry.get_sample_value(gauge_no_labels._name), 123.0)

        gauge_with_labels = metrics.CPU_USAGE
        labels = {'core': '1'}
        metrics.set_gauge_metric(gauge_with_labels, 55.5, labels=labels)
        self.assertEqual(self.registry.get_sample_value(gauge_with_labels._name, labels), 55.5)

    def test_observe_histogram_metric(self):
        """Test the histogram observe helper function."""
        histo = metrics.REQUEST_LATENCY
        labels = {'endpoint': '/data'}
        metrics.observe_histogram_metric(histo, 0.1, labels=labels)
        metrics.observe_histogram_metric(histo, 0.2, labels=labels)
        metrics.observe_histogram_metric(histo, 0.3, labels=labels)

        self.assertEqual(self.registry.get_sample_value(f'{histo._name}_count', labels), 3.0)
        
        # Added a type guard to satisfy the type checker for assertAlmostEqual
        sum_val = self.registry.get_sample_value(f'{histo._name}_sum', labels)
        self.assertIsNotNone(sum_val)
        if sum_val is not None:
            self.assertAlmostEqual(sum_val, 0.6)
            
        # Check one of the buckets
        self.assertEqual(self.registry.get_sample_value(f'{histo._name}_bucket', {**labels, 'le': '0.25'}), 2.0)

    def test_get_metrics_output(self):
        """Test that get_metrics returns the serialized data from the registry."""
        metrics.increment_counter_metric(metrics.ESCALATION_REQUESTS_RECEIVED)
        # Replaced undefined metric with 'ACTIVE_USERS'
        metrics.set_gauge_metric(metrics.ACTIVE_USERS, 42)
        
        output = metrics.get_metrics().decode('utf-8')
        
        self.assertIn('# HELP escalation_requests_received_total Total number of requests received by the escalation engine', output)
        self.assertIn('escalation_requests_received_total 1.0', output)
        # Replaced undefined metric with 'ACTIVE_USERS'
        self.assertIn('active_users_current 42.0', output)

    def test_invalid_metric_type_for_helpers(self):
        """Test that helpers raise errors for incorrect metric types."""
        counter = metrics.REQUEST_COUNT
        # Replaced undefined metric with 'ACTIVE_USERS'
        gauge = metrics.ACTIVE_USERS
        histo = metrics.REQUEST_LATENCY

        with self.assertRaises(TypeError):
            metrics.set_gauge_metric(counter, 10) # Can't set a counter
        with self.assertRaises(TypeError):
            metrics.observe_histogram_metric(gauge, 0.5) # Can't observe a gauge
        with self.assertRaises(TypeError):
            metrics.increment_counter_metric(histo) # Can't increment a histogram

if __name__ == '__main__':
    unittest.main()
