# test/admin_ui/test_plugin_discovery.py
import os
import tempfile
import unittest
from unittest.mock import patch

from src.admin_ui.admin_ui import _discover_plugins


class TestPluginDiscovery(unittest.TestCase):
    def test_discovers_sorted_python_modules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "a.py"), "w").close()
            open(os.path.join(tmpdir, "b.py"), "w").close()
            open(os.path.join(tmpdir, "_c.py"), "w").close()
            open(os.path.join(tmpdir, "d.txt"), "w").close()
            with patch.dict(os.environ, {"PLUGIN_DIR": tmpdir}):
                self.assertEqual(_discover_plugins(), ["a", "b"])

    def test_missing_directory_returns_empty_list(self):
        with patch.dict(os.environ, {"PLUGIN_DIR": "/no/such/dir"}):
            self.assertEqual(_discover_plugins(), [])
