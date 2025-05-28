# test\tarpit\ip_flagger.test.py
import unittest
from tarpit.ip_flagger import IPFlagger

class TestIPFlagger(unittest.TestCase):

    def setUp(self):
        self.flagger = IPFlagger()

    def test_flag_ip_adds_ip(self):
        self.flagger.flag("192.168.1.1")
        self.assertIn("192.168.1.1", self.flagger.flagged_ips)

    def test_unflag_removes_ip(self):
        self.flagger.flag("10.0.0.1")
        self.flagger.unflag("10.0.0.1")
        self.assertNotIn("10.0.0.1", self.flagger.flagged_ips)

    def test_is_flagged_true(self):
        self.flagger.flag("8.8.8.8")
        self.assertTrue(self.flagger.is_flagged("8.8.8.8"))

    def test_is_flagged_false(self):
        self.assertFalse(self.flagger.is_flagged("1.1.1.1"))

    def test_clear_flags(self):
        self.flagger.flag("1.2.3.4")
        self.flagger.clear()
        self.assertEqual(len(self.flagger.flagged_ips), 0)

if __name__ == '__main__':
    unittest.main()
