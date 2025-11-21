# test/shared/metrics.test.py
import importlib
import sys
import unittest
from unittest.mock import patch

try:  # pragma: no cover
    from prometheus_client import CollectorRegistry
except ImportError:  # pragma: no cover
    CollectorRegistry = None  # type: ignore[assignment]

from src.shared import metrics


@unittest.skipIf(CollectorRegistry is None, "prometheus_client not installed")
class TestMetricsComprehensive(unittest.TestCase):

    def setUp(self):
        """
        Create a new registry for each test to ensure isolation.
        We will patch the REGISTRY object in the metrics module.
        """
        self.registry = CollectorRegistry()
        # Patch CollectorRegistry at the source to ensure all metrics use the custom registry
        with patch("prometheus_client.CollectorRegistry", return_value=self.registry):
            importlib.reload(metrics)

    def tearDown(self):
        """Reload the metrics module to restore the default registry."""
        importlib.reload(metrics)

    def test_increment_counter_metric(self):
        """Test the counter helper function with and without labels."""
        # Test counter without labels
        counter_no_labels = metrics.TARPIT_ENTRIES
        metrics.increment_counter_metric(counter_no_labels)
        metrics.increment_counter_metric(counter_no_labels)
        self.assertEqual(
            self.registry.get_sample_value(f"{counter_no_labels._name}_total"), 2.0
        )

        # Test counter with labels
        counter_with_labels = metrics.REQUEST_COUNT
        labels = {"method": "GET", "endpoint": "/api", "status_code": "200"}
        metrics.increment_counter_metric(counter_with_labels, labels=labels)
        self.assertEqual(
            self.registry.get_sample_value(
                f"{counter_with_labels._name}_total", labels
            ),
            1.0,
        )

    def test_increment_counter_metric_in_memory(self):
        """Ensure increment_counter_metric works with the in-memory counter."""
        counter = metrics.InMemoryCounter("test")
        metrics.increment_counter_metric(counter)
        metrics.increment_counter_metric(counter)
        self.assertEqual(counter.get(), 2)

        labels = {"foo": "bar"}
        metrics.increment_counter_metric(counter, labels=labels)
        self.assertEqual(counter.get(**labels), 1)

    def test_set_gauge_metric(self):
        """Test the gauge set helper function with and without labels."""
        # Replaced undefined metric with 'ACTIVE_USERS' which is defined in metrics.py
        gauge_no_labels = metrics.ACTIVE_USERS
        metrics.set_gauge_metric(gauge_no_labels, 123)
        self.assertEqual(self.registry.get_sample_value(gauge_no_labels._name), 123.0)

        gauge_with_labels = metrics.CPU_USAGE
        labels = {"core": "1"}
        metrics.set_gauge_metric(gauge_with_labels, 55.5, labels=labels)
        self.assertEqual(
            self.registry.get_sample_value(gauge_with_labels._name, labels), 55.5
        )

    def test_observe_histogram_metric(self):
        """Test the histogram observe helper function."""
        histo = metrics.REQUEST_LATENCY
        labels = {"method": "GET", "endpoint": "/data"}
        metrics.observe_histogram_metric(histo, 0.1, labels=labels)
        metrics.observe_histogram_metric(histo, 0.2, labels=labels)
        metrics.observe_histogram_metric(histo, 0.3, labels=labels)

        self.assertEqual(
            self.registry.get_sample_value(f"{histo._name}_count", labels), 3.0
        )

        # Added a type guard to satisfy the type checker for assertAlmostEqual
        sum_val = self.registry.get_sample_value(f"{histo._name}_sum", labels)
        self.assertIsNotNone(sum_val)
        if sum_val is not None:
            self.assertAlmostEqual(sum_val, 0.6)

        # Check one of the buckets
        self.assertEqual(
            self.registry.get_sample_value(
                f"{histo._name}_bucket", {**labels, "le": "0.25"}
            ),
            2.0,
        )

    def test_get_metrics_output(self):
        """Test that get_metrics returns the serialized data from the registry."""
        metrics.increment_counter_metric(metrics.ESCALATION_REQUESTS_RECEIVED)
        # Replaced undefined metric with 'ACTIVE_USERS'
        metrics.set_gauge_metric(metrics.ACTIVE_USERS, 42)

        output = metrics.get_metrics().decode("utf-8")

        self.assertIn(
            "# HELP escalation_requests_received_total Total number of requests received by the escalation engine",
            output,
        )
        self.assertIn("escalation_requests_received_total 1.0", output)
        # Replaced undefined metric with 'ACTIVE_USERS'
        self.assertIn("active_users_current 42.0", output)

    def test_invalid_metric_type_for_helpers(self):
        """Test that helpers raise errors for incorrect metric types."""
        counter = metrics.REQUEST_COUNT
        # Replaced undefined metric with 'ACTIVE_USERS'
        gauge = metrics.ACTIVE_USERS
        histo = metrics.REQUEST_LATENCY

        with self.assertRaises(TypeError):
            metrics.set_gauge_metric(counter, 10)  # Can't set a counter
        with self.assertRaises(TypeError):
            metrics.observe_histogram_metric(gauge, 0.5)  # Can't observe a gauge
        with self.assertRaises(TypeError):
            metrics.increment_counter_metric(histo)  # Can't increment a histogram


class TestMetricsFallback(unittest.TestCase):
    def test_in_memory_metrics_when_prometheus_missing(self):
        with patch.dict(sys.modules, {"prometheus_client": None}):
            importlib.reload(metrics)
            counter = metrics.REQUEST_COUNT
            metrics.increment_counter_metric(counter)
            self.assertEqual(counter.get(), 1)
            output = metrics.get_metrics().decode("utf-8")
            self.assertIn("http_requests_total", output)
        importlib.reload(metrics)

    def test_in_memory_metrics_with_labels_when_prometheus_missing(self):
        with patch.dict(sys.modules, {"prometheus_client": None}):
            importlib.reload(metrics)
            counter = metrics.REQUEST_COUNT
            metrics.increment_counter_metric(
                counter,
                labels={
                    "method": "GET",
                    "endpoint": "/a",
                    "status_code": "200",
                },
            )
            metrics.increment_counter_metric(
                counter,
                labels={
                    "method": "POST",
                    "endpoint": "/b",
                    "status_code": "500",
                },
            )
            output = metrics.get_metrics().decode("utf-8")
            self.assertIn(
                'http_requests_total_total{endpoint="/a",method="GET",status_code="200"} 1',
                output,
            )
            self.assertIn(
                'http_requests_total_total{endpoint="/b",method="POST",status_code="500"} 1',
                output,
            )
        importlib.reload(metrics)


class TestPerformanceMetrics(unittest.TestCase):
    def setUp(self):
        """Create a new registry for each test."""
        self.registry = CollectorRegistry()
        with patch("prometheus_client.CollectorRegistry", return_value=self.registry):
            importlib.reload(metrics)

    def tearDown(self):
        """Reload the metrics module to restore the default registry."""
        importlib.reload(metrics)

    def test_performance_baseline_gauge(self):
        """Test performance baseline gauge."""
        gauge = metrics.PERFORMANCE_BASELINE
        metrics.set_gauge_metric(gauge, 0.5, labels={"metric_name": "latency", "service": "api"})
        self.assertEqual(
            self.registry.get_sample_value(
                gauge._name, {"metric_name": "latency", "service": "api"}
            ),
            0.5,
        )

    def test_performance_anomaly_score_gauge(self):
        """Test performance anomaly score gauge."""
        gauge = metrics.PERFORMANCE_ANOMALY_SCORE
        metrics.set_gauge_metric(gauge, 0.8, labels={"metric_name": "latency", "service": "api"})
        self.assertEqual(
            self.registry.get_sample_value(
                gauge._name, {"metric_name": "latency", "service": "api"}
            ),
            0.8,
        )

    def test_performance_trend_gauge(self):
        """Test performance trend gauge."""
        gauge = metrics.PERFORMANCE_TREND
        metrics.set_gauge_metric(gauge, -0.5, labels={"metric_name": "latency", "service": "api"})
        self.assertEqual(
            self.registry.get_sample_value(
                gauge._name, {"metric_name": "latency", "service": "api"}
            ),
            -0.5,
        )

    def test_performance_samples_counter(self):
        """Test performance samples counter."""
        counter = metrics.PERFORMANCE_SAMPLES_COLLECTED
        metrics.increment_counter_metric(
            counter, labels={"metric_name": "latency", "service": "api"}
        )
        metrics.increment_counter_metric(
            counter, labels={"metric_name": "latency", "service": "api"}
        )
        self.assertEqual(
            self.registry.get_sample_value(
                f"{counter._name}_total", {"metric_name": "latency", "service": "api"}
            ),
            2.0,
        )

    def test_performance_predictions_counter(self):
        """Test performance predictions counter."""
        counter = metrics.PERFORMANCE_PREDICTIONS_GENERATED
        metrics.increment_counter_metric(
            counter, labels={"prediction_type": "capacity", "service": "api"}
        )
        self.assertEqual(
            self.registry.get_sample_value(
                f"{counter._name}_total", {"prediction_type": "capacity", "service": "api"}
            ),
            1.0,
        )

    def test_performance_insights_counter(self):
        """Test performance insights counter."""
        counter = metrics.PERFORMANCE_INSIGHTS_GENERATED
        metrics.increment_counter_metric(
            counter, labels={"insight_type": "degradation", "service": "api"}
        )
        self.assertEqual(
            self.registry.get_sample_value(
                f"{counter._name}_total", {"insight_type": "degradation", "service": "api"}
            ),
            1.0,
        )

    def test_performance_degradation_counter(self):
        """Test performance degradation counter."""
        counter = metrics.PERFORMANCE_DEGRADATION_DETECTED
        metrics.increment_counter_metric(
            counter, labels={"metric_name": "latency", "service": "api"}
        )
        self.assertEqual(
            self.registry.get_sample_value(
                f"{counter._name}_total", {"metric_name": "latency", "service": "api"}
            ),
            1.0,
        )

    def test_performance_percentile_histogram(self):
        """Test performance percentile histogram."""
        histo = metrics.PERFORMANCE_PERCENTILE
        labels = {"metric_name": "latency", "service": "api"}
        metrics.observe_histogram_metric(histo, 0.1, labels=labels)
        metrics.observe_histogram_metric(histo, 0.2, labels=labels)
        self.assertEqual(
            self.registry.get_sample_value(f"{histo._name}_count", labels), 2.0
        )


if __name__ == "__main__":
    unittest.main()
