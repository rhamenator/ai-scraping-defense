import unittest
from unittest.mock import MagicMock, patch

from src.escalation import escalation_engine as ee


class TestGeoIPLookup(unittest.TestCase):
    def test_get_country_code(self):
        fake_resp = MagicMock()
        fake_resp.country.iso_code = "US"
        fake_reader = MagicMock()
        fake_reader.country.return_value = fake_resp
        with patch("geoip2.database.Reader", return_value=fake_reader):
            with patch.object(ee, "GEOIP_DB_PATH", "/tmp/db.mmdb"):
                ee._geoip_reader = None
                code = ee.get_country_code("1.1.1.1")
        self.assertEqual(code, "US")
