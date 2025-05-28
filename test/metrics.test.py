# test/metrics.test.py
import unittest
import time
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, Summary # Import Summary
# Assuming metrics.py is in the parent directory or accessible via PYTHONPATH
import metrics 

class TestMetrics(unittest.TestCase):

    def setUp(self):
        """
        Clear samples from known metrics in the global metrics.REGISTRY before each test.
        This attempts to reset the state of metrics for test isolation.
        """
        # List of all metric objects defined in metrics.py
        # This needs to be kept in sync if new metrics are added to metrics.py
        known_metrics_to_clear = [
            metrics.REQUEST_COUNT, metrics.PAGE_VIEWS, metrics.CACHE_HITS, metrics.CACHE_MISSES,
            metrics.DB_QUERIES, metrics.ERROR_COUNT, metrics.SECURITY_EVENTS, metrics.LOGIN_ATTEMPTS,
            metrics.USER_REGISTRATIONS, metrics.API_CALLS, metrics.EXTERNAL_API_CALLS,
            metrics.FILE_UPLOADS, metrics.EMAIL_SENT, metrics.TARPIT_ENTRIES, metrics.HONEYPOT_TRIGGERS,
            metrics.REQUEST_LATENCY, metrics.DB_QUERY_LATENCY, metrics.EXTERNAL_API_LATENCY,
            metrics.FUNCTION_EXECUTION_TIME, metrics.FILE_UPLOAD_SIZE, metrics.RESPONSE_SIZE,
            metrics.ACTIVE_USERS, metrics.CPU_USAGE, metrics.MEMORY_USAGE, metrics.DISK_SPACE_USAGE,
            metrics.DB_CONNECTIONS, metrics.QUEUE_LENGTH, metrics.UPTIME_SECONDS,
            metrics.CELERY_WORKERS, metrics.CELERY_TASKS, metrics.FEATURE_FLAGS
        ]

        for metric_obj in known_metrics_to_clear:
            # For Counter, Gauge, Histogram, which store their children in _metrics (internal)
            # and don't have a public clear method for all samples.
            # We can remove all labeled children, which effectively clears them.
            if hasattr(metric_obj, '_metrics') and metric_obj._metrics: # Check if _metrics exists and is not empty
                # For metrics with labels, clear out the children.
                # This is an internal API, but often used in tests.
                metric_obj_children = list(metric_obj._metrics.keys()) # Get a static list of keys
                for child_labels in metric_obj_children:
                    try:
                        if hasattr(metric_obj, 'remove'):
                             metric_obj.remove(*child_labels)
                        # For some types, re-initializing the specific label set might be an option
                        # or simply relying on the fact that new tests won't reuse exact old label sets
                        # if the metric was without labels, this loop won't run for _metrics.keys()
                    except Exception:
                        # Fallback or log if needed, some metrics might not support remove for all cases
                        pass
            
            # If it's a metric without labels and has a _value (like a simple Gauge/Counter without labels)
            # resetting it requires specific handling not generically available via a 'clear'
            # For simple no-label counters/gauges, their value is often part of the main object.
            # prometheus-client doesn't offer a direct "reset to zero" for no-label counters.
            # Gauges can be set to 0.
            if isinstance(metric_obj, Gauge) and not metric_obj._labelnames: # No-label Gauge
                try:
                    metric_obj.set(0) # Reset no-label gauge to 0
                except Exception:
                    pass # Should not happen for a simple gauge

        # Special handling for Summary if any are used and need clearing
        # (No Summaries in the provided metrics.py, but good for future)
        # for collector in list(metrics.REGISTRY._collector_to_names.keys()):
        #     if isinstance(collector, Summary) and hasattr(collector, 'clear'):
        #         collector.clear()
        
        # Note: The most robust way to ensure test isolation with prometheus-client
        # is often to use a new CollectorRegistry() for each test or to unregister
        # and re-register metrics. Given the global REGISTRY in metrics.py,
        # this approach of attempting to clear/reset known metrics is a compromise.


    def _get_metric_sample_value(self, metric_name, labels=None):
        """Helper to safely get a sample value from the registry. Returns float or None."""
        val = metrics.REGISTRY.get_sample_value(metric_name, labels=labels)
        return float(val) if val is not None else None

    def _get_histogram_samples(self, histogram_metric, target_labels=None):
        """
        Helper to get sum and count for a histogram series. Returns (float | None, float | None).
        """
        metric_name = histogram_metric._name # Assumes histogram_metric has _name
        h_sum = None
        h_count = None
        
        collected_metrics = histogram_metric.collect()
        if not collected_metrics:
            return None, None
        
        for sample in collected_metrics[0].samples:
            current_labels = sample.labels
            # Ensure target_labels is a dict if not None, for consistent comparison
            effective_target_labels = target_labels if target_labels is not None else {}

            if current_labels == effective_target_labels:
                if sample.name == f"{metric_name}_sum":
                    h_sum = float(sample.value)
                if sample.name == f"{metric_name}_count":
                    h_count = float(sample.value)
        return h_sum, h_count


    def test_record_request(self):
        """Test the record_request helper function."""
        metric_name = metrics.REQUEST_COUNT._name # Use the metric's actual name attribute
        labels1 = {'method': 'GET', 'endpoint': '/test_endpoint', 'status_code': '200'}
        
        initial_value1 = self._get_metric_sample_value(metric_name, labels1) or 0.0
        metrics.record_request('GET', '/test_endpoint', 200)
        new_value1 = self._get_metric_sample_value(metric_name, labels1)
        self.assertIsNotNone(new_value1, "Metric sample should exist after recording.")
        self.assertEqual(new_value1, initial_value1 + 1.0)

        labels2 = {'method': 'POST', 'endpoint': '/another_endpoint', 'status_code': '201'}
        initial_value2 = self._get_metric_sample_value(metric_name, labels2) or 0.0
        metrics.record_request('POST', '/another_endpoint', 201)
        new_value2 = self._get_metric_sample_value(metric_name, labels2)
        self.assertIsNotNone(new_value2)
        self.assertEqual(new_value2, initial_value2 + 1.0)


    def test_example_timed_request_handler(self):
        """Test the @REQUEST_LATENCY.time() decorator via example_timed_request_handler."""
        target_labels = {'method': 'GET', 'endpoint': '/example'}
        
        initial_sum, initial_count = self._get_histogram_samples(metrics.REQUEST_LATENCY, target_labels)
        initial_sum = initial_sum or 0.0
        initial_count = initial_count or 0.0

        metrics.example_timed_request_handler() 

        final_sum, final_count = self._get_histogram_samples(metrics.REQUEST_LATENCY, target_labels)
        
        self.assertIsNotNone(final_sum, "Sum sample should exist.")
        self.assertIsNotNone(final_count, "Count sample should exist.")
        # Ensure types are float for comparison
        self.assertEqual(float(final_count or 0.0), float(initial_count or 0.0) + 1.0)
        self.assertGreaterEqual(float(final_sum or 0.0), float(initial_sum or 0.0) + 0.09, "Recorded duration too short.")
        self.assertLess(float(final_sum or 0.0), float(initial_sum or 0.0) + 0.2, "Recorded duration too long.")


    def test_observe_histogram_metric(self):
        """Test observe_histogram_metric with and without labels."""
        labeled_hist_metric = metrics.DB_QUERY_LATENCY
        labels = {'query_type': 'SELECT_TEST_OBSERVE'}
        
        initial_sum_labeled, initial_count_labeled = self._get_histogram_samples(labeled_hist_metric, labels)
        initial_sum_labeled = initial_sum_labeled or 0.0
        initial_count_labeled = initial_count_labeled or 0.0

        metrics.observe_histogram_metric(labeled_hist_metric, 0.05, labels=labels)

        final_sum_labeled, final_count_labeled = self._get_histogram_samples(labeled_hist_metric, labels)

        self.assertIsNotNone(final_sum_labeled)
        self.assertIsNotNone(final_count_labeled)
        self.assertEqual(float(final_count_labeled or 0.0), float(initial_count_labeled or 0.0) + 1.0)
        self.assertIsNotNone(final_sum_labeled)
        self.assertIsNotNone(initial_sum_labeled)
        # Ensure both values are not None before conversion
        self.assertAlmostEqual(float(final_sum_labeled or 0.0), float(initial_sum_labeled or 0.0) + 0.05)

        temp_hist_no_labels_name = "temp_hist_observe_no_labels_seconds"
        # Unregister if already exists from a previous failed run
        # Accessing REGISTRY._collector_to_names is internal; be cautious.
        # A safer way would be to try/except the registration of the temp metric.
        for coll in list(metrics.REGISTRY._collector_to_names.keys()): # Iterate over a copy
            # Use collect() to get the metric family and check its name
            try:
                families = list(coll.collect())
                if families and getattr(families[0], 'name', None) == temp_hist_no_labels_name:
                    metrics.REGISTRY.unregister(coll)
                    break
            except Exception:
                continue
        
        temp_hist_no_labels = Histogram(temp_hist_no_labels_name, 
                                        "Temp hist for observe_histogram_metric without labels", 
                                        registry=metrics.REGISTRY)
        try:
            initial_sum_nl, initial_count_nl = self._get_histogram_samples(temp_hist_no_labels, target_labels=None) # Pass None for no-label series
            initial_sum_nl = initial_sum_nl or 0.0
            initial_count_nl = initial_count_nl or 0.0
            
            metrics.observe_histogram_metric(temp_hist_no_labels, 0.789)

            final_sum_nl, final_count_nl = self._get_histogram_samples(temp_hist_no_labels, target_labels=None)

            self.assertIsNotNone(final_sum_nl, "Sum for no-label hist should exist.")
            self.assertIsNotNone(final_count_nl, "Count for no-label hist should exist.")
            self.assertEqual(float(final_count_nl or 0.0), float(initial_count_nl or 0.0) + 1.0)
            self.assertAlmostEqual(float(final_sum_nl or 0.0), float(initial_sum_nl or 0.0) + 0.789)
        finally:
            metrics.REGISTRY.unregister(temp_hist_no_labels)


    def test_increment_counter_metric(self):
        """Test increment_counter_metric with and without labels."""
        labeled_counter_metric = metrics.PAGE_VIEWS
        labels = {'page_type': 'test_page_increment'}
        metric_name_labeled = labeled_counter_metric._name
        
        initial_value_labeled = self._get_metric_sample_value(metric_name_labeled, labels) or 0.0
        metrics.increment_counter_metric(labeled_counter_metric, labels=labels)
        new_value_labeled = self._get_metric_sample_value(metric_name_labeled, labels)
        self.assertIsNotNone(new_value_labeled)
        self.assertEqual(new_value_labeled, initial_value_labeled + 1.0)

        no_label_counter_metric = metrics.USER_REGISTRATIONS
        metric_name_no_label = no_label_counter_metric._name
        initial_value_no_label = self._get_metric_sample_value(metric_name_no_label) or 0.0
        
        metrics.increment_counter_metric(no_label_counter_metric)
        new_value_no_label = self._get_metric_sample_value(metric_name_no_label)
        self.assertIsNotNone(new_value_no_label)
        self.assertEqual(new_value_no_label, initial_value_no_label + 1.0)


    def test_set_gauge_metric(self):
        """Test set_gauge_metric with and without labels."""
        no_label_gauge_metric = metrics.ACTIVE_USERS
        metric_name_no_label = no_label_gauge_metric._name
        
        metrics.set_gauge_metric(no_label_gauge_metric, 123.0)
        self.assertEqual(self._get_metric_sample_value(metric_name_no_label), 123.0)
        metrics.set_gauge_metric(no_label_gauge_metric, 100.0)
        self.assertEqual(self._get_metric_sample_value(metric_name_no_label), 100.0)

        labeled_gauge_metric = metrics.CPU_USAGE
        labels = {'core': 'test_core_set'}
        metric_name_labeled = labeled_gauge_metric._name
        
        metrics.set_gauge_metric(labeled_gauge_metric, 55.5, labels=labels)
        self.assertEqual(self._get_metric_sample_value(metric_name_labeled, labels), 55.5)


    def test_increment_gauge_metric(self):
        """Test increment_gauge_metric with and without labels."""
        labeled_gauge_metric = metrics.QUEUE_LENGTH
        labels = {'queue_name': 'test_queue_increment'}
        metric_name_labeled = labeled_gauge_metric._name

        metrics.set_gauge_metric(labeled_gauge_metric, 5.0, labels=labels)
        initial_value_labeled = self._get_metric_sample_value(metric_name_labeled, labels)
        self.assertEqual(initial_value_labeled, 5.0)

        metrics.increment_gauge_metric(labeled_gauge_metric, labels=labels)
        new_value_labeled = self._get_metric_sample_value(metric_name_labeled, labels)
        self.assertIsNotNone(new_value_labeled)
        # Ensure initial_value_labeled is float before arithmetic
        self.assertEqual(new_value_labeled, (initial_value_labeled or 0.0) + 1.0)


        no_label_gauge_metric = metrics.UPTIME_SECONDS
        metric_name_no_label = no_label_gauge_metric._name
        
        metrics.set_gauge_metric(no_label_gauge_metric, 1000.0)
        initial_value_no_label = self._get_metric_sample_value(metric_name_no_label)
        self.assertEqual(initial_value_no_label, 1000.0)

        metrics.increment_gauge_metric(no_label_gauge_metric)
        new_value_no_label = self._get_metric_sample_value(metric_name_no_label)
        self.assertIsNotNone(new_value_no_label)
        self.assertEqual(new_value_no_label, (initial_value_no_label or 0.0) + 1.0)


    def test_decrement_gauge_metric(self):
        """Test decrement_gauge_metric with and without labels."""
        labeled_gauge_metric = metrics.DB_CONNECTIONS
        labels = {'db_name': 'test_db_decrement', 'state': 'active_decrement'}
        metric_name_labeled = labeled_gauge_metric._name

        metrics.set_gauge_metric(labeled_gauge_metric, 10.0, labels=labels)
        initial_value_labeled = self._get_metric_sample_value(metric_name_labeled, labels)
        self.assertEqual(initial_value_labeled, 10.0)
        
        metrics.decrement_gauge_metric(labeled_gauge_metric, labels=labels)
        new_value_labeled = self._get_metric_sample_value(metric_name_labeled, labels)
        self.assertIsNotNone(new_value_labeled)
        self.assertEqual(new_value_labeled, (initial_value_labeled or 0.0) - 1.0)

        no_label_gauge_metric = metrics.ACTIVE_USERS
        metric_name_no_label = no_label_gauge_metric._name
        
        metrics.set_gauge_metric(no_label_gauge_metric, 50.0)
        initial_value_no_label = self._get_metric_sample_value(metric_name_no_label)
        self.assertEqual(initial_value_no_label, 50.0)

        metrics.decrement_gauge_metric(no_label_gauge_metric)
        new_value_no_label = self._get_metric_sample_value(metric_name_no_label)
        self.assertIsNotNone(new_value_no_label)
        self.assertEqual(new_value_no_label, (initial_value_no_label or 0.0) - 1.0)


    def test_get_metrics_output(self):
        """Test the output of get_metrics after various operations."""
        self.setUp()
        
        metrics.record_request('GET', '/metrics_output_test', 200)
        metrics.increment_counter_metric(metrics.PAGE_VIEWS, labels={'page_type': 'metrics_output_page'})
        metrics.set_gauge_metric(metrics.ACTIVE_USERS, 42.0)
        metrics.observe_histogram_metric(metrics.REQUEST_LATENCY, 0.01, labels={'method': 'PUT', 'endpoint': '/put_output_test'})
        metrics.increment_counter_metric(metrics.USER_REGISTRATIONS)

        output = metrics.get_metrics()
        output_str = output.decode('utf-8')

        self.assertIn(f"# HELP {metrics.REQUEST_COUNT._name} {metrics.REQUEST_COUNT._documentation}", output_str)
        self.assertIn(f"# TYPE {metrics.REQUEST_COUNT._name} counter", output_str)
        # ... (other HELP/TYPE checks)

        self.assertIn('http_requests_total{endpoint="/metrics_output_test",method="GET",status_code="200"} 1.0', output_str)
        self.assertIn('page_views_total{page_type="metrics_output_page"} 1.0', output_str)
        self.assertIn('active_users_current 42.0', output_str)
        # ... (other sample data checks)


    def test_get_metrics_output_clean_registry(self):
        """Test get_metrics output when no samples have been recorded (after setup)."""
        self.setUp() 

        output = metrics.get_metrics()
        output_str = output.decode('utf-8')

        self.assertIn(f"# HELP {metrics.REQUEST_COUNT._name} {metrics.REQUEST_COUNT._documentation}", output_str)
        self.assertIn(f"# TYPE {metrics.REQUEST_COUNT._name} counter", output_str)
        
        self.assertNotIn('http_requests_total{', output_str)
        # For gauges, if setUp resets them to 0, they might still appear with 0.0
        # If setUp doesn't set them, they shouldn't appear.
        # The current setUp tries to set no-label gauges to 0.
        if self._get_metric_sample_value(metrics.ACTIVE_USERS._name) == 0.0:
             self.assertIn(f'{metrics.ACTIVE_USERS._name} 0.0', output_str)
        else:
             self.assertNotIn(f'{metrics.ACTIVE_USERS._name} ', output_str)
        

    def test_all_metrics_definitions_registered(self):
        """Check if all defined metric objects are registered in REGISTRY and have correct types."""
        defined_metrics_instances = [
            metrics.REQUEST_COUNT, metrics.PAGE_VIEWS, metrics.CACHE_HITS, metrics.CACHE_MISSES, 
            metrics.DB_QUERIES, metrics.ERROR_COUNT, metrics.SECURITY_EVENTS, metrics.LOGIN_ATTEMPTS, 
            metrics.USER_REGISTRATIONS, metrics.API_CALLS, metrics.EXTERNAL_API_CALLS,
            metrics.FILE_UPLOADS, metrics.EMAIL_SENT, metrics.TARPIT_ENTRIES, metrics.HONEYPOT_TRIGGERS,
            metrics.REQUEST_LATENCY, metrics.DB_QUERY_LATENCY, metrics.EXTERNAL_API_LATENCY, 
            metrics.FUNCTION_EXECUTION_TIME, metrics.FILE_UPLOAD_SIZE, metrics.RESPONSE_SIZE,
            metrics.ACTIVE_USERS, metrics.CPU_USAGE, metrics.MEMORY_USAGE, metrics.DISK_SPACE_USAGE, 
            metrics.DB_CONNECTIONS, metrics.QUEUE_LENGTH, metrics.UPTIME_SECONDS, 
            metrics.CELERY_WORKERS, metrics.CELERY_TASKS, metrics.FEATURE_FLAGS
        ]

        # metrics.REGISTRY._collector_to_names is internal.
        # A better check is to see if generating metrics includes their names.
        # However, for type checking, we can iterate through our known list.
        
        for metric_instance in defined_metrics_instances:
            # Check if the metric instance itself is in the list of collectors keys
            # This is an internal detail of prometheus_client, might be fragile
            self.assertIn(metric_instance, metrics.REGISTRY._collector_to_names.keys(),
                          f"Metric instance for {metric_instance._name} should be registered.")
            
            if isinstance(metric_instance, Counter):
                self.assertEqual(metric_instance._type, "counter")
            elif isinstance(metric_instance, Gauge):
                 self.assertEqual(metric_instance._type, "gauge")
            elif isinstance(metric_instance, Histogram):
                 self.assertEqual(metric_instance._type, "histogram")
            # Add Summary if you use it
            # elif isinstance(metric_instance, Summary):
            #      self.assertEqual(metric_instance._type, "summary")
            else:
                self.fail(f"Metric {metric_instance._name} has an unrecognized type: {type(metric_instance)}")

if __name__ == '__main__':
    unittest.main(verbosity=2)
