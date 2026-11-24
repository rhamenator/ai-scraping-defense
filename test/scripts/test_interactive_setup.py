import http.client
import json
import secrets
import tempfile
import threading
import unittest
import urllib.parse
from http.server import ThreadingHTTPServer
from pathlib import Path

from scripts import interactive_setup, interactive_setup_web


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


class TestInteractiveSetupWeb(unittest.TestCase):
    @staticmethod
    def _request(port: int, method: str, path: str, body: str | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        headers = {"Content-Type": "application/x-www-form-urlencoded"} if body else {}
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        return resp.status, data

    def test_web_setup_requires_token_and_saves_env_without_exposing_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            mask_marker = "demo-mask-check-value"
            env_path.write_text(
                f"REAL_BACKEND_HOST=https://old.example.com\nNGINX_HTTP_PORT=8080\nOPENAI_API_KEY={mask_marker}\n"
            )
            state = {
                "env_file": env_path,
                "bootstrap_token": secrets.token_urlsafe(16),
                "session_token": secrets.token_urlsafe(16),
                "csrf_token": secrets.token_urlsafe(16),
                "parse_env": interactive_setup.parse_env,
                "apply_updates": lambda updates: interactive_setup.update_env_file(env_path, updates),
                "key_settings": interactive_setup.KEY_SETTINGS,
                "optional_features": interactive_setup.OPTIONAL_FEATURES,
                "is_secret": interactive_setup.is_secret_key,
                "shutdown_on_save": False,
            }
            server = ThreadingHTTPServer(("127.0.0.1", 0), interactive_setup_web.create_setup_handler(state))
            state["server"] = server
            threading.Thread(target=server.serve_forever, daemon=True).start()
            port = server.server_address[1]
            try:
                status_no_tok, _ = self._request(port, "GET", "/")
                self.assertEqual(status_no_tok, 403)
                status_ok, body = self._request(port, "GET", f"/?token={state['bootstrap_token']}")
                self.assertEqual(status_ok, 200)
                self.assertIn("https://old.example.com", body)
                self.assertNotIn(mask_marker, body)

                payload = urllib.parse.urlencode(
                    {
                        "csrf_token": state["csrf_token"],
                        "cfg_REAL_BACKEND_HOST": "https://new.example.com",
                        "feat_ENABLE_MCP_MODEL": "true",
                    }
                )
                post_status, _ = self._request(
                    port, "POST", f"/save?token={state['bootstrap_token']}", body=payload
                )
                self.assertEqual(post_status, 200)
                parsed = interactive_setup.parse_env(env_path)
                self.assertEqual(parsed["REAL_BACKEND_HOST"], "https://new.example.com")
                self.assertEqual(parsed["NGINX_HTTP_PORT"], "8080")
                self.assertEqual(parsed["OPENAI_API_KEY"], mask_marker)
                self.assertEqual(parsed["MODEL_URI"], "mcp://primary/classify")
            finally:
                server.shutdown()
                server.server_close()
