# test\rag\email_entropy_scanner.test.py
import unittest
from rag.email_entropy_scanner import EntropyScanner

class TestEntropyScanner(unittest.TestCase):

    def setUp(self):
        self.scanner = EntropyScanner()

    def test_entropy_simple_email(self):
        email = "test@example.com"
        entropy = self.scanner.calculate_entropy(email)
        self.assertGreater(entropy, 0)

    def test_entropy_empty_string(self):
        entropy = self.scanner.calculate_entropy("")
        self.assertEqual(entropy, 0.0)

    def test_entropy_high_entropy_email(self):
        email = "x1y2z3a4b5c6d7e8f9g0@example.com"
        entropy = self.scanner.calculate_entropy(email)
        self.assertGreater(entropy, 3.5)

    def test_is_suspicious_true(self):
        suspicious_email = "abcd1234!@weird-domain.com"
        self.assertTrue(self.scanner.is_suspicious(suspicious_email))

    def test_is_suspicious_false(self):
        normal_email = "jane.doe@example.com"
        self.assertFalse(self.scanner.is_suspicious(normal_email))

if __name__ == '__main__':
    unittest.main()
