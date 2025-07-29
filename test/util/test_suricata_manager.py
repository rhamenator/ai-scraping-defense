import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.util import suricata_manager


class TestSuricataManager(unittest.TestCase):
    def test_parse_eve_alerts(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
            tmp.write('{"event_type":"alert","src_ip":"1.1.1.1"}\n')
            tmp.write('{"event_type":"stats"}\n')
            path = tmp.name
        alerts = suricata_manager.parse_eve_alerts(path)
        os.unlink(path)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["src_ip"], "1.1.1.1")

    def test_process_eve_log_sends(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
            tmp.write('{"event_type":"alert","src_ip":"2.2.2.2"}\n')
            eve_path = tmp.name
        with patch.object(suricata_manager, "EVE_LOG_PATH", eve_path), patch(
            "src.util.suricata_manager.send_alert_to_escalation"
        ) as mock_send:
            mock_send.return_value = True
            count = suricata_manager.process_eve_log()
            self.assertEqual(count, 1)
            mock_send.assert_called_once()
        os.unlink(eve_path)


if __name__ == "__main__":
    unittest.main()
