import unittest

from src.tarpit import obfuscation


class TestObfuscation(unittest.TestCase):
    def test_generate_fingerprinting_script_heavyweight(self):
        script = obfuscation.generate_fingerprinting_script()
        self.assertIn("navigator.userAgent", script)
        self.assertIn("screen.width", script)
        self.assertIn("screen.colorDepth", script)
        self.assertIn("navigator.language", script)
        self.assertIn("navigator.platform", script)
        self.assertIn("getTimezoneOffset", script)
        self.assertIn("navigator.hardwareConcurrency", script)
        self.assertIn("navigator.plugins", script)
        self.assertIn("document.fonts", script)


if __name__ == "__main__":
    unittest.main()
