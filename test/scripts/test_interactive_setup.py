import json
import tempfile
import unittest
from pathlib import Path

from scripts import interactive_setup


class TestInteractiveSetupState(unittest.TestCase):
    def test_secret_key_detection(self):
        self.assertTrue(interactive_setup.is_secret_key("CLOUD_CDN_API_TOKEN"))
        self.assertTrue(interactive_setup.is_secret_key("ADMIN_UI_PASSWORD_HASH"))
        self.assertFalse(interactive_setup.is_secret_key("REAL_BACKEND_HOST"))

    def test_save_and_load_state_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / ".state.json"
            interactive_setup.save_setup_state(state_path, {"MODEL_URI", "ENABLE_WAF"})
            loaded = interactive_setup.load_setup_state(state_path)
            self.assertEqual(
                sorted(loaded.get("completed_keys", [])), ["ENABLE_WAF", "MODEL_URI"]
            )

    def test_load_state_handles_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / ".state.json"
            state_path.write_text("{invalid json")
            loaded = interactive_setup.load_setup_state(state_path)
            self.assertEqual(loaded, {})

    def test_clear_state_removes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / ".state.json"
            state_path.write_text(json.dumps({"completed_keys": ["MODEL_URI"]}))
            interactive_setup.clear_setup_state(state_path)
            self.assertFalse(state_path.exists())
