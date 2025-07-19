# test/tarpit/ip_flagger.test.py
import unittest
from unittest.mock import patch, MagicMock
from redis.exceptions import RedisError, ConnectionError
import logging

from src.tarpit import ip_flagger
import importlib

class TestIPFlaggerComprehensive(unittest.TestCase):

    def setUp(self):
        """Set up mock Redis connection for each test."""
        # Reload the module to clear any cached clients
        importlib.reload(ip_flagger)
        self.get_redis_patcher = patch('src.tarpit.ip_flagger.get_redis_connection')
        self.mock_get_redis = self.get_redis_patcher.start()
        self.mock_redis_client = MagicMock()
        self.mock_get_redis.return_value = self.mock_redis_client

    def tearDown(self):
        """Stop the patcher and re-enable logging."""
        self.get_redis_patcher.stop()

    def test_flag_suspicious_ip_success(self):
        """Test that a suspicious IP is successfully flagged in Redis."""
        self.mock_redis_client.incr.return_value = 1
        result = ip_flagger.flag_suspicious_ip("8.8.8.8", "Test Reason: High frequency")

        self.assertTrue(result)
        self.mock_get_redis.assert_called_once_with(db_number=ip_flagger.REDIS_DB_FLAGGED_IPS)
        self.mock_redis_client.setex.assert_called_once_with("default:ip_flag:8.8.8.8", ip_flagger.FLAGGED_IP_TTL_SECONDS, "Test Reason: High frequency")
        self.mock_redis_client.expire.assert_called_once()

    def test_flag_suspicious_ip_redis_connection_fails(self):
        """Test that flagging fails gracefully if Redis connection is unavailable."""
        self.mock_get_redis.return_value = None
        
        with self.assertLogs('src.tarpit.ip_flagger', level='ERROR') as cm:
            result = ip_flagger.flag_suspicious_ip("8.8.8.8", "Test Reason")
            self.assertFalse(result)
            self.assertIn("Redis unavailable", cm.output[0])

    def test_flag_suspicious_ip_redis_command_error(self):
        """Test that flagging fails gracefully on a Redis command error."""
        self.mock_redis_client.incr.side_effect = RedisError("Command failed")

        with self.assertLogs('src.tarpit.ip_flagger', level='ERROR') as cm:
            result = ip_flagger.flag_suspicious_ip("8.8.8.8", "Test Reason")
            self.assertFalse(result)
            self.assertIn("Failed to flag IP", cm.output[0])

    def test_is_ip_flagged_true(self):
        """Test checking a flagged IP returns True."""
        self.mock_redis_client.exists.return_value = 1
        result = ip_flagger.is_ip_flagged("9.9.9.9")
        self.assertTrue(result)
        self.mock_redis_client.exists.assert_called_once_with("default:ip_flag:9.9.9.9")

    def test_is_ip_flagged_false(self):
        """Test checking an unflagged IP returns False."""
        self.mock_redis_client.exists.return_value = 0
        result = ip_flagger.is_ip_flagged("10.10.10.10")
        self.assertFalse(result)

    def test_is_ip_flagged_redis_unavailable(self):
        """Test that checking an IP returns False if Redis is unavailable."""
        self.mock_get_redis.return_value = None
        with self.assertLogs('src.tarpit.ip_flagger', level='ERROR') as cm:
            result = ip_flagger.is_ip_flagged("9.9.9.9")
            self.assertFalse(result)
            self.assertIn("Redis unavailable", cm.output[0])
            
    def test_remove_ip_flag_success(self):
        """Test successfully removing an IP flag."""
        self.mock_redis_client.delete.return_value = 1
        result = ip_flagger.remove_ip_flag("8.8.8.8")
        self.assertTrue(result)
        self.mock_redis_client.delete.assert_any_call("default:ip_flag:8.8.8.8")
        self.mock_redis_client.delete.assert_any_call(f"{ip_flagger.FLAG_COUNT_PREFIX}8.8.8.8")
        
    def test_remove_ip_flag_redis_command_error(self):
        """Test graceful failure when removing an IP flag throws an error."""
        self.mock_redis_client.delete.side_effect = ConnectionError("Connection lost")
        with self.assertLogs('src.tarpit.ip_flagger', level='ERROR') as cm:
            result = ip_flagger.remove_ip_flag("8.8.8.8")
            self.assertFalse(result)
            self.assertIn("Failed to remove IP flag", cm.output[0])

if __name__ == '__main__':
    unittest.main()
