import importlib
import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.cloud_dashboard import cloud_dashboard_api as cd
from src.shared.observability import WebSocketConnectionLimiter

OPERATOR = {"X-API-Key": "test-secret"}


class MockRedis:
    def __init__(self):
        self.store = {}

    def set(self, key, value, ex=None):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)


class Base(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"CLOUD_DASHBOARD_API_KEY": "test-secret"}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        importlib.reload(cd)
        self.redis = MockRedis()
        patcher = patch("src.cloud_dashboard.cloud_dashboard_api.get_redis_connection", return_value=self.redis)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(cd.app, headers=OPERATOR)  # the operator
        self.addCleanup(self.client.close)

    def register(self, installation_id, **extra):
        resp = self.client.post("/register", json={"installation_id": installation_id, **extra})
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def installation(self, installation_id):
        """Register an installation and return a client that authenticates as it."""
        token = self.register(installation_id)["token"]
        client = TestClient(cd.app, headers={cd.INSTALLATION_CREDENTIAL_HEADER: token})
        self.addCleanup(client.close)
        return client, token


class Basics(Base):
    def test_register_push_and_read(self):
        inst, _ = self.installation("inst1")
        self.assertEqual(inst.post("/metrics", json={"installation_id": "inst1", "metrics": {"requests": 5}}).status_code, 200)
        self.assertEqual(inst.get("/metrics/inst1").json(), {"requests": 5})
        self.assertEqual(self.client.get("/metrics/inst1").json(), {"requests": 5}, "the operator reads any installation")

    def test_push_invalid_payload(self):
        resp = self.client.post("/metrics", json={"installation_id": "x"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    def test_rejects_long_installation_id(self):
        resp = self.client.post("/register", json={"installation_id": "a" * 200})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    def test_missing_api_key_configuration_fails_closed(self):
        with patch.object(cd, "API_KEY", None):
            response = self.client.post("/register", json={"installation_id": "closed"})
            self.assertEqual(response.status_code, 503)
            with self.assertRaises(WebSocketDisconnect):
                with self.client.websocket_connect("/ws/closed"):
                    pass

    def test_unauthenticated_requests_are_refused(self):
        bare = TestClient(cd.app)
        self.addCleanup(bare.close)
        self.assertEqual(bare.post("/register", json={"installation_id": "x"}).status_code, 401)
        self.assertEqual(bare.post("/metrics", json={"installation_id": "x", "metrics": {}}).status_code, 401)
        self.assertEqual(bare.get("/metrics/x").status_code, 401)
        with self.assertRaises(WebSocketDisconnect):
            with bare.websocket_connect("/ws/x"):
                pass


class InstallationIsolation(Base):
    def test_installation_a_cannot_read_push_or_register_for_b(self):
        a, _ = self.installation("inst-a")
        b, _ = self.installation("inst-b")
        b.post("/metrics", json={"metrics": {"private_b": 1}})
        self.assertEqual(a.get("/metrics/inst-b").status_code, 403)
        self.assertEqual(a.post("/metrics", json={"installation_id": "inst-b", "metrics": {"x": 1}}).status_code, 403)
        self.assertEqual(a.post("/register", json={"installation_id": "inst-b"}).status_code, 403)
        self.assertEqual(self.client.get("/metrics/inst-b").json(), {"private_b": 1}, "B's data was not overwritten")

    def test_installation_a_cannot_open_bs_websocket(self):
        a, token_a = self.installation("inst-a")
        self.installation("inst-b")
        with self.assertRaises(WebSocketDisconnect):
            with a.websocket_connect("/ws/inst-b"):
                pass
        with a.websocket_connect("/ws/inst-a") as ws:
            self.assertEqual(ws.receive_json(), {})

    def test_the_installation_id_comes_from_the_credential(self):
        a, _ = self.installation("inst-a")
        self.assertEqual(a.post("/metrics", json={"metrics": {"k": 2}}).status_code, 200)
        self.assertEqual(a.get("/metrics/inst-a").json(), {"k": 2})

    def test_unknown_ids_and_bad_credentials_fail_closed_the_same_way(self):
        _, token = self.installation("inst-a")
        secret = token.rsplit(".", 1)[1]
        bad = {
            "wrong secret": f"inst-a.{'x' * len(secret)}",
            "unknown id": f"ghost.{secret}",
            "id swapped in": f"inst-b.{secret}",
            "no dot": "inst-a",
            "empty secret": "inst-a.",
            "empty": "",
        }
        for name, value in bad.items():
            with self.subTest(name=name):
                client = TestClient(cd.app, headers={cd.INSTALLATION_CREDENTIAL_HEADER: value} if value else {})
                self.addCleanup(client.close)
                self.assertEqual(client.get("/metrics/inst-a").status_code, 401)
                self.assertEqual(client.post("/metrics", json={"installation_id": "inst-a", "metrics": {}}).status_code, 401)

    def test_a_valid_token_does_not_fall_back_to_the_operator_key(self):
        a, token = self.installation("inst-a")
        both = TestClient(cd.app, headers={**OPERATOR, cd.INSTALLATION_CREDENTIAL_HEADER: f"inst-a.{'y' * 43}"})
        self.addCleanup(both.close)
        self.assertEqual(both.get("/metrics/inst-a").status_code, 401, "a bad installation token is not rescued by an operator key")


class Credentials(Base):
    def test_the_token_is_shown_once_and_only_its_hash_is_stored(self):
        first = self.register("inst-a")
        token = first["token"]
        self.assertTrue(token.startswith("inst-a."))
        self.assertNotIn("token", self.register("inst-a"), "registering again does not reveal or change the credential")
        stored = " ".join(str(v) for v in self.redis.store.values())
        self.assertNotIn(token.rsplit(".", 1)[1], stored)
        credential = json.loads(self.redis.store[cd._credential_key("inst-a")])
        self.assertRegex(credential["hash"], r"^[0-9a-f]{64}$")

    def test_rotation_invalidates_the_old_token(self):
        old_client, _ = self.installation("inst-a")
        new_token = self.register("inst-a", rotate=True)["token"]
        self.assertEqual(old_client.get("/metrics/inst-a").status_code, 401)
        fresh = TestClient(cd.app, headers={cd.INSTALLATION_CREDENTIAL_HEADER: new_token})
        self.addCleanup(fresh.close)
        self.assertEqual(fresh.get("/metrics/inst-a").status_code, 200)

    def test_an_installation_can_refresh_its_registration_but_not_rotate_its_credential(self):
        a, token = self.installation("inst-a")
        resp = a.post("/register", json={"installation_id": "inst-a", "rotate": True})
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("token", resp.json())
        self.assertEqual(a.get("/metrics/inst-a").status_code, 200, "its credential is unchanged")

    def test_tokens_are_random(self):
        self.assertNotEqual(self.register("i1")["token"].split(".", 1)[1], self.register("i2")["token"].split(".", 1)[1])


class KeyNamespaces(Base):
    """An installation id chosen to look like another installation's key must not reach that installation's state."""

    def test_an_installation_named_like_a_credential_key_cannot_overwrite_a_victims_credential(self):
        victim_client, victim_token = self.installation("victim")
        attacker, _ = self.installation("credential:victim")
        forged = {"hash": cd._hash_secret("attacker-chosen"), "created": 0}
        attacker.post("/metrics", json={"metrics": forged})

        forged_token = "victim." + "attacker-chosen"
        impostor = TestClient(cd.app, headers={cd.INSTALLATION_CREDENTIAL_HEADER: forged_token})
        self.addCleanup(impostor.close)
        self.assertEqual(impostor.get("/metrics/victim").status_code, 401, "the forged credential must not authenticate")
        self.assertEqual(victim_client.get("/metrics/victim").status_code, 200, "the victim's own credential still works")

    def test_an_installation_named_like_a_registration_key_cannot_forge_a_registration(self):
        attacker, _ = self.installation("registered:ghost")
        attacker.post("/metrics", json={"metrics": {"x": 1}})
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect("/ws/ghost"):
                pass

    def test_the_three_kinds_of_state_use_distinct_prefixes(self):
        keys = {cd._metrics_key("a:b"), cd._credential_key("a:b"), cd._registration_key("a:b")}
        self.assertEqual(len(keys), 3)
        prefixes = {k.split(":")[2] for k in keys}
        self.assertEqual(prefixes, {"metrics", "credential", "install"})


class OperatorCredential(Base):
    def test_the_shared_key_cannot_push_for_an_installation_by_default(self):
        self.register("inst-a")
        resp = self.client.post("/metrics", json={"installation_id": "inst-a", "metrics": {"x": 1}})
        self.assertEqual(resp.status_code, 403)

    def test_the_legacy_opt_in_restores_shared_key_pushes(self):
        self.register("inst-a")
        with patch.object(cd, "ALLOW_SHARED_KEY", True):
            resp = self.client.post("/metrics", json={"installation_id": "inst-a", "metrics": {"x": 1}})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.client.get("/metrics/inst-a").json(), {"x": 1})


class WebSocket(Base):
    def test_streams_metrics_and_fanout(self):
        inst, _ = self.installation("ws1")
        with self.client.websocket_connect("/ws/ws1") as ws:
            self.assertEqual(ws.receive_json(), {})
            inst.post("/metrics", json={"installation_id": "ws1", "metrics": {"m": 1}})
            self.assertEqual(ws.receive_json(), {"m": 1})

    def test_watchers_entry_removed_when_empty(self):
        self.installation("ws2")
        with self.client.websocket_connect("/ws/ws2"):
            self.assertIn("ws2", cd.WATCHERS)
        self.assertNotIn("ws2", cd.WATCHERS)

    def test_requires_registered_installation(self):
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect("/ws/unregistered"):
                pass

    def test_rejects_when_connection_limit_exceeded(self):
        self.installation("ws-limit")
        with patch.object(cd, "WEBSOCKET_LIMITER", WebSocketConnectionLimiter(max_total=1, max_per_key=1)):
            with self.client.websocket_connect("/ws/ws-limit") as first:
                self.assertEqual(first.receive_json(), {})
                with self.assertRaises(WebSocketDisconnect):
                    with self.client.websocket_connect("/ws/ws-limit"):
                        pass

    @patch("src.cloud_dashboard.cloud_dashboard_api.log_event")
    def test_rejection_is_audited(self, mock_log_event):
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect("/ws/not-registered"):
                pass
        mock_log_event.assert_called()
        self.assertIn("denied", mock_log_event.call_args.args[1])

    @patch("src.cloud_dashboard.cloud_dashboard_api.log_event")
    def test_a_cross_installation_attempt_is_audited_with_its_reason(self, mock_log_event):
        a, _ = self.installation("inst-a")
        self.installation("inst-b")
        with self.assertRaises(WebSocketDisconnect):
            with a.websocket_connect("/ws/inst-b"):
                pass
        self.assertEqual(mock_log_event.call_args.args[2]["reason"], "wrong_installation")

    def test_rejects_oversized_payload(self):
        inst, _ = self.installation("ws-big")
        inst.post("/metrics", json={"installation_id": "ws-big", "metrics": {"blob": "x" * 128}})
        with patch.object(cd, "MAX_WEBSOCKET_MESSAGE_BYTES", 32):
            with self.client.websocket_connect("/ws/ws-big") as ws:
                self.assertEqual(ws.receive_json(), {"error": "Metrics payload too large"})
                with self.assertRaises(WebSocketDisconnect):
                    ws.receive_json()


if __name__ == "__main__":
    unittest.main()
