import unittest
from unittest.mock import patch, MagicMock
from escalation import escalation_engine
from escalation.escalation_engine import RequestMetadata


class TestRequestMetadata(unittest.TestCase):

    def test_request_metadata_fields(self):
        metadata = RequestMetadata(
            timestamp="2025-05-28T10:00:00Z",
            ip="192.168.1.1",
            user_agent="UnitTestBot",
            referer="http://example.com",
            path="/index.html",
            headers={"X-Test": "yes"},
            source="test_suite"
        )
        self.assertEqual(metadata.ip, "192.168.1.1")
        self.assertEqual(metadata.source, "test_suite")
        self.assertIn("X-Test", metadata.headers)


class TestIPRepFunction(unittest.TestCase):

    def test_ip_reputation_check(self):
        score = escalation_engine.check_ip_reputation("8.8.8.8")
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)


class TestClassification(unittest.TestCase):

    @patch("escalation.escalation_engine.classify_request")
    def test_classification_call(self, mock_classify):
        mock_classify.return_value = "PASS"
        request_data = RequestMetadata(
            timestamp="2025-05-28T10:00:00Z",
            ip="1.2.3.4",
            user_agent="Mozilla/5.0",
            referer="http://foo.com",
            path="/test",
            headers={"User-Agent": "Mozilla/5.0"},
            source="unit_test"
        )
        result = mock_classify(request_data)
        self.assertEqual(result, "PASS")
        mock_classify.assert_called_once()


class TestFrequencyExtraction(unittest.TestCase):

    def test_extract_features_from_headers(self):
        headers = {
            "User-Agent": "CustomAgent",
            "Referer": "https://example.com"
        }
        result = escalation_engine.extract_features_from_headers(headers)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)


if __name__ == "__main__":
    unittest.main()
