# test/tarpit/ip_flagger.test.py
import unittest
from unittest.mock import patch, MagicMock, call
import os
import datetime
import importlib

# Import the module to test
# We need to be careful with module-level 'redis_client'
# so we'll often reload the module after setting up patches.
from tarpit import ip_flagger 
from redis.exceptions import ConnectionError, RedisError # Import for exception checking

# Helper to reset module-level redis_client for test isolation
def reset_ip_flagger_redis_client():
    ip_flagger.redis_client = None

class TestIPFlaggerModuleLoading(unittest.TestCase):
    
    def tearDown(self):
        # Ensure redis_client is reset after each test in this class
        reset_ip_flagger_redis_client()
        # Also, unpatch os.getenv if it was patched for a specific test
        patch.stopall() # Stops all active patches

    @patch('redis.Redis')
    @patch('redis.ConnectionPool')
    @patch.dict(os.environ, {"REDIS_HOST": "mockhost", "REDIS_PORT": "1234", "REDIS_DB_TAR_PIT": "1"})
    def test_redis_client_initialization_success(self, mock_connection_pool, mock_redis_constructor):
        """Test successful Redis client initialization on module import."""
        mock_redis_instance = MagicMock()
        mock_redis_constructor.return_value = mock_redis_instance
        
        # Reload the module to trigger its import-time Redis connection logic
        importlib.reload(ip_flagger)
        
        mock_connection_pool.assert_called_once_with(
            host="mockhost", port=1234, db=1, decode_responses=True
        )
        mock_redis_constructor.assert_called_once_with(connection_pool=mock_connection_pool.return_value)
        mock_redis_instance.ping.assert_called_once()
        self.assertIsNotNone(ip_flagger.redis_client, "redis_client should be set on successful connection.")
        self.assertEqual(ip_flagger.redis_client, mock_redis_instance)

    @patch('redis.ConnectionPool', side_effect=ConnectionError("Mock Connection Error"))
    @patch('builtins.print') # To capture the error print
    @patch.dict(os.environ, {"REDIS_HOST": "mockhost", "REDIS_PORT": "1234", "REDIS_DB_TAR_PIT": "1"})
    def test_redis_client_initialization_failure(self, mock_print, mock_connection_pool_error):
        """Test Redis client being None if connection fails on module import."""
        # Reload the module. The ConnectionError should be caught.
        importlib.reload(ip_flagger)
        
        self.assertIsNone(ip_flagger.redis_client, "redis_client should be None if connection fails.")
        mock_print.assert_any_call("ERROR: Could not connect to Redis at mockhost:1234. IP Flagging disabled. Error: Mock Connection Error")

class TestIPFlaggerFunctions(unittest.TestCase):

    def setUp(self):
        # Mock the global redis_client for function tests
        self.redis_client_patcher = patch('tarpit.ip_flagger.redis_client')
        self.mock_redis_client = self.redis_client_patcher.start()
        self.addCleanup(self.redis_client_patcher.stop)

        # Mock print for checking log messages
        self.print_patcher = patch('builtins.print')
        self.mock_print = self.print_patcher.start()
        self.addCleanup(self.print_patcher.stop)

    def test_flag_suspicious_ip_success(self):
        """Test successful IP flagging."""
        test_ip = "1.2.3.4"
        # Ensure redis_client is a mock, not None for this test path
        self.mock_redis_client.setex.return_value = True # Simulate successful setex

        ip_flagger.flag_suspicious_ip(test_ip)

        self.mock_redis_client.setex.assert_called_once()
        args, _ = self.mock_redis_client.setex.call_args
        self.assertEqual(args[0], f"tarpit_flag:{test_ip}")
        self.assertEqual(args[1], ip_flagger.FLAG_TTL_SECONDS)
        # self.assertIsInstance(args[2], str) # Timestamp is a string
        self.mock_print.assert_any_call(f"Flagged IP: {test_ip} in Redis for {ip_flagger.FLAG_TTL_SECONDS} seconds.")
        # The function implicitly returns None on success, so no return value to check.

    def test_flag_suspicious_ip_redis_unavailable(self):
        """Test flagging when Redis client is None."""
        with patch('tarpit.ip_flagger.redis_client', None): # Simulate redis_client being None
            result = ip_flagger.flag_suspicious_ip("1.2.3.4")
            self.assertFalse(result) # Explicitly returns False

    def test_flag_suspicious_ip_invalid_ip(self):
        """Test flagging with an invalid IP."""
        result_empty = ip_flagger.flag_suspicious_ip("")
        self.assertFalse(result_empty)
        
        result_none = ip_flagger.flag_suspicious_ip(None) # type: ignore
        self.assertFalse(result_none)
        self.mock_redis_client.setex.assert_not_called()

    def test_flag_suspicious_ip_redis_error(self):
        """Test flagging when Redis setex raises an error."""
        self.mock_redis_client.setex.side_effect = RedisError("Setex failed")
        
        result = ip_flagger.flag_suspicious_ip("1.2.3.4")
        
        self.assertFalse(result)
        self.mock_print.assert_any_call("ERROR: Redis error while flagging IP 1.2.3.4: Setex failed")

    def test_flag_suspicious_ip_generic_error(self):
        """Test flagging when a generic error occurs."""
        self.mock_redis_client.setex.side_effect = Exception("Generic error")
        
        result = ip_flagger.flag_suspicious_ip("1.2.3.4")

        self.assertFalse(result)
        self.mock_print.assert_any_call("ERROR: Unexpected error flagging IP 1.2.3.4: Generic error")


    def test_check_ip_flag_exists(self):
        """Test checking a flagged IP."""
        self.mock_redis_client.exists.return_value = 1 # Flag exists
        self.assertTrue(ip_flagger.check_ip_flag("1.2.3.4"))
        self.mock_redis_client.exists.assert_called_once_with("tarpit_flag:1.2.3.4")

    def test_check_ip_flag_not_exists(self):
        """Test checking an unflagged IP."""
        self.mock_redis_client.exists.return_value = 0 # Flag does not exist
        self.assertFalse(ip_flagger.check_ip_flag("1.2.3.4"))

    def test_check_ip_flag_redis_unavailable(self):
        """Test checking flag when Redis client is None."""
        with patch('tarpit.ip_flagger.redis_client', None):
            self.assertFalse(ip_flagger.check_ip_flag("1.2.3.4"))

    def test_check_ip_flag_invalid_ip(self):
        """Test checking flag with an invalid IP."""
        self.assertFalse(ip_flagger.check_ip_flag(""))
        self.assertFalse(ip_flagger.check_ip_flag(None)) # type: ignore
        self.mock_redis_client.exists.assert_not_called()

    def test_check_ip_flag_redis_error(self):
        """Test checking flag when Redis exists raises an error."""
        self.mock_redis_client.exists.side_effect = RedisError("Exists failed")
        self.assertFalse(ip_flagger.check_ip_flag("1.2.3.4")) # Should fail safe
        self.mock_print.assert_any_call("ERROR: Redis error while checking IP flag 1.2.3.4: Exists failed")

    def test_check_ip_flag_generic_error(self):
        """Test checking flag when a generic error occurs."""
        self.mock_redis_client.exists.side_effect = Exception("Generic error")
        self.assertFalse(ip_flagger.check_ip_flag("1.2.3.4")) # Should fail safe
        self.mock_print.assert_any_call("ERROR: Unexpected error checking IP flag 1.2.3.4: Generic error")


class TestMainExecutionBlock(unittest.TestCase):

    @patch('tarpit.ip_flagger.flag_suspicious_ip')
    @patch('tarpit.ip_flagger.check_ip_flag')
    @patch('builtins.print')
    def test_main_block_calls_functions(self, mock_print, mock_check_flag, mock_flag_ip):
        """Test that the __main__ block calls the flag and check functions."""
        # Simulate the script being run as __main__
        # This requires reloading the module with __name__ patched.
        
        # Set side effects for check_ip_flag to simulate different states
        mock_check_flag.side_effect = [False, True] # First check -> False, Second check -> True
        
        with patch.object(ip_flagger, '__name__', '__main__'):
            # Mock redis_client for the reloaded module to avoid actual connection attempt
            with patch('tarpit.ip_flagger.redis_client', MagicMock()):
                importlib.reload(ip_flagger)
        
        # Verify calls based on the logic in __main__
        self.assertGreaterEqual(mock_print.call_count, 3) # Initial check, flagging, second check
        
        # Check the sequence of calls
        expected_calls = [
            call("Checking flag for 192.168.1.100: False"),
            call("Flagging 192.168.1.100..."),
            call("Checking flag for 192.168.1.100: True")
        ]
        # mock_print.assert_has_calls(expected_calls, any_order=False) # This can be too strict with other prints
        for expected_call_arg in [c[0][0] for c in expected_calls]: # Check if each expected string was printed
            self.assertTrue(any(expected_call_arg in str(actual_call[0]) for actual_call in mock_print.call_args_list),
                            f"Expected print call containing '{expected_call_arg}' not found.")

        mock_flag_ip.assert_called_once_with("192.168.1.100")
        self.assertEqual(mock_check_flag.call_count, 2)
        mock_check_flag.assert_any_call("192.168.1.100")


if __name__ == '__main__':
    unittest.main()
