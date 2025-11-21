import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import operations_toolkit


class TestOperationsToolkit(unittest.TestCase):
    def test_backup_returns_timestamped_path(self):
        """Test that backup() returns the timestamped directory path."""
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(
                destination=tmp,
                postgres_url="postgres://test",
                redis_url="redis://test",
                kube_context="test-context",
                execute=False,
            )
            
            with patch("scripts.operations_toolkit.run_command") as mock_run:
                mock_run.return_value = operations_toolkit.CommandResult(
                    command=[], returncode=0, stdout="", stderr=""
                )
                result_path = operations_toolkit.backup(args)
                
                # Verify the returned path is under the destination
                self.assertTrue(str(result_path).startswith(tmp))
                # Verify the path includes a timestamp subdirectory
                self.assertNotEqual(str(result_path), tmp)
                # Verify the path exists (was created by ensure_directory)
                self.assertTrue(result_path.exists())

    def test_disaster_recovery_drill_uses_correct_backup_path(self):
        """Test that disaster_recovery_drill passes the correct timestamped path to restore."""
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(
                environment="staging",
                drill_backup_dir=tmp,
                postgres_url="postgres://test",
                redis_url="redis://test",
                kube_context="test-context",
                redis_data_dir="/var/lib/redis",
                redis_host="localhost",
                execute=False,
            )
            
            with patch("scripts.operations_toolkit.run_command") as mock_run:
                mock_run.return_value = operations_toolkit.CommandResult(
                    command=[], returncode=0, stdout="", stderr=""
                )
                
                with patch("scripts.operations_toolkit.restore") as mock_restore:
                    operations_toolkit.disaster_recovery_drill(args)
                    
                    # Verify restore was called
                    self.assertEqual(mock_restore.call_count, 1)
                    
                    # Get the arguments passed to restore
                    restore_args = mock_restore.call_args[0][0]
                    
                    # Verify the source path is a timestamped subdirectory, not the parent
                    self.assertTrue(restore_args.source.startswith(tmp))
                    self.assertNotEqual(restore_args.source, tmp)
                    
                    # Verify required redis parameters are present
                    self.assertEqual(restore_args.redis_data_dir, "/var/lib/redis")
                    self.assertEqual(restore_args.redis_host, "localhost")
                    
                    # Verify other parameters are passed correctly
                    self.assertEqual(restore_args.postgres_url, "postgres://test")
                    self.assertEqual(restore_args.redis_url, "redis://test")
                    self.assertFalse(restore_args.execute)

    def test_disaster_recovery_drill_namespace_no_duplicates(self):
        """Test that the restore Namespace has no duplicate parameters."""
        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(
                environment="staging",
                drill_backup_dir=tmp,
                postgres_url="postgres://test",
                redis_url="redis://test",
                kube_context="test-context",
                redis_data_dir="/var/lib/redis",
                redis_host="localhost",
                execute=False,
            )
            
            with patch("scripts.operations_toolkit.run_command") as mock_run:
                mock_run.return_value = operations_toolkit.CommandResult(
                    command=[], returncode=0, stdout="", stderr=""
                )
                
                with patch("scripts.operations_toolkit.restore") as mock_restore:
                    operations_toolkit.disaster_recovery_drill(args)
                    
                    # Get the arguments passed to restore
                    restore_args = mock_restore.call_args[0][0]
                    
                    # Get all attribute names from the Namespace
                    attrs = vars(restore_args)
                    
                    # Verify each required attribute exists exactly once
                    required_attrs = ["source", "postgres_url", "redis_url", 
                                      "redis_data_dir", "redis_host", "execute"]
                    for attr in required_attrs:
                        self.assertIn(attr, attrs, f"Missing required attribute: {attr}")


if __name__ == "__main__":
    unittest.main()
