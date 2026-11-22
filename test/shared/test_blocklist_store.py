"""Every blocklist writer must produce exactly what the edge reads, and unblocking must undo it (#1902)."""

import os
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from redis.exceptions import RedisError

from src.shared import blocklist_store as store
from src.shared.config import CONFIG
from test.fake_blocklist_redis import FakeBlocklistRedis

LUA = (Path(__file__).resolve().parents[2] / "nginx" / "lua" / "blocklist.lua").read_text()


def edge_key(ip: str, tenant: str = "default") -> str:
    """The key the Lua check looks up, built the way the Lua builds it."""
    assert 'key_prefix = tenant_id .. ":blocklist:ip:"' in LUA
    assert 'os.getenv("TENANT_ID") or "default"' in LUA
    return f"{tenant}:blocklist:ip:{ip}"


class EdgeContract(unittest.TestCase):
    def test_the_database_and_key_shape_match_what_the_lua_reads(self):
        self.assertEqual(store.block_key("203.0.113.5"), edge_key("203.0.113.5"))
        self.assertIn('tonumber(os.getenv("REDIS_DB_BLOCKLIST")) or 2', LUA)
        self.assertEqual(CONFIG.REDIS_DB_BLOCKLIST, int(os.getenv("REDIS_DB_BLOCKLIST", 2)))

    def test_the_edge_normalises_ipv4_mapped_clients_the_way_the_store_does(self):
        self.assertIn('"^::[fF][fF][fF][fF]:(%d+%.%d+%.%d+%.%d+)$"', LUA)
        self.assertEqual(store.normalize_ip("::ffff:203.0.113.5"), "203.0.113.5")

    def test_each_writer_blocks_the_key_the_edge_reads(self):
        ip = "203.0.113.20"
        # admin UI / signed webhook / anything calling the store directly
        fake = FakeBlocklistRedis()
        self.assertTrue(store.block(ip, "manual", source="admin_ui", conn=fake))
        self.assertEqual(fake.exists(edge_key(ip)), 1)

        # the tarpit
        from src.tarpit import tarpit_api

        fake = FakeBlocklistRedis()
        with patch.object(tarpit_api, "redis_blocklist", fake):
            self.assertTrue(tarpit_api.trigger_ip_block(ip, "tarpit"))
        self.assertEqual(fake.exists(edge_key(ip)), 1)
        self.assertGreater(fake.ttl(edge_key(ip)), 0, "automated blocks expire")

        # the escalation engine's helper
        from src.ai_service import blocklist as engine

        fake = FakeBlocklistRedis()
        with patch.object(engine, "get_redis_connection", return_value=fake), patch.object(engine, "BLOCKLISTING_ENABLED", True):
            self.assertTrue(engine.add_ip_to_blocklist(ip, "engine"))
        self.assertEqual(fake.exists(edge_key(ip)), 1)

    def test_the_old_shapes_are_gone(self):
        fake = FakeBlocklistRedis()
        store.block("203.0.113.21", "x", source="admin_ui", conn=fake)
        self.assertEqual(sorted(fake.data), [edge_key("203.0.113.21")], "no set, no legacy key")


class BlockAndUnblock(unittest.TestCase):
    def setUp(self):
        self.fake = FakeBlocklistRedis()

    def test_unblock_removes_exactly_the_key_the_block_created(self):
        store.block("203.0.113.30", "x", source="admin_ui", conn=self.fake)
        store.block("203.0.113.31", "x", source="admin_ui", conn=self.fake)
        self.assertTrue(store.unblock("203.0.113.30", conn=self.fake))
        self.assertEqual(self.fake.exists(edge_key("203.0.113.30")), 0)
        self.assertEqual(self.fake.exists(edge_key("203.0.113.31")), 1)

    def test_unblock_also_clears_legacy_copies(self):
        self.fake.sadd("default:blocklist", "203.0.113.32")
        self.fake.set("default:blocklist:203.0.113.32", "reason")
        self.assertTrue(store.unblock("203.0.113.32", conn=self.fake))
        self.assertEqual(self.fake.smembers("default:blocklist"), set())
        self.assertEqual(self.fake.exists("default:blocklist:203.0.113.32"), 0)

    def test_ttl_is_applied_only_when_asked_for(self):
        store.block("203.0.113.40", "x", source="tarpit", ttl_seconds=120, conn=self.fake)
        store.block("203.0.113.41", "x", source="admin_ui", conn=self.fake)
        store.block("203.0.113.42", "x", source="admin_ui", ttl_seconds=0, conn=self.fake)
        self.assertGreater(self.fake.ttl(edge_key("203.0.113.40")), 0)
        self.assertEqual(self.fake.ttl(edge_key("203.0.113.41")), -1)
        self.assertEqual(self.fake.ttl(edge_key("203.0.113.42")), -1)

    def test_ipv4_ipv6_and_mapped_forms_share_one_key(self):
        store.block("::ffff:203.0.113.50", "x", source="admin_ui", conn=self.fake)
        store.block("2001:0db8:0000:0000:0000:0000:0000:0001", "x", source="admin_ui", conn=self.fake)
        self.assertEqual(sorted(self.fake.data), sorted([edge_key("203.0.113.50"), edge_key("2001:db8::1")]))
        self.assertTrue(store.unblock("2001:db8:0::1", conn=self.fake))
        self.assertTrue(store.is_blocked("203.0.113.50", conn=self.fake))
        self.assertFalse(store.is_blocked("2001:db8::1", conn=self.fake))

    def test_invalid_addresses_are_refused(self):
        for bad in ("", "unknown", "not-an-ip", "300.1.1.1", "1.2.3"):
            self.assertFalse(store.block(bad, "x", source="admin_ui", conn=self.fake), bad)
        self.assertEqual(self.fake.data, {})

    def test_tenants_are_kept_apart(self):
        with patch("src.shared.blocklist_store.tenant_key", side_effect=lambda base, tenant_id=None: f"acme:{base}"):
            store.block("203.0.113.60", "x", source="admin_ui", conn=self.fake)
        self.assertEqual(list(self.fake.data), [edge_key("203.0.113.60", tenant="acme")])
        self.assertFalse(store.is_blocked("203.0.113.60", conn=self.fake), "another tenant's block is not ours")

    def test_success_is_reported_only_after_the_key_is_read_back(self):
        conn = MagicMock()
        conn.exists.return_value = 0  # the write "succeeded" but the key is not there
        self.assertFalse(store.block("203.0.113.70", "x", source="admin_ui", conn=conn))
        broken = FakeBlocklistRedis()
        broken.fail_with = RedisError("down")
        self.assertFalse(store.block("203.0.113.70", "x", source="admin_ui", conn=broken))
        self.assertFalse(store.unblock("203.0.113.70", conn=broken))

    def test_unblock_reports_failure_if_the_key_is_still_there(self):
        conn = MagicMock()
        conn.exists.return_value = 1
        self.assertFalse(store.unblock("203.0.113.71", conn=conn))


class PermanentBlocksAreProtected(unittest.TestCase):
    def setUp(self):
        self.fake = FakeBlocklistRedis()

    def test_a_temporary_block_never_replaces_a_permanent_one(self):
        store.block("203.0.113.100", "admin", source="admin_ui", conn=self.fake)

        self.assertTrue(store.block("203.0.113.100", "tarpit", source="tarpit", ttl_seconds=60, conn=self.fake))

        self.assertEqual(self.fake.ttl(edge_key("203.0.113.100")), -1, "still permanent")
        self.assertIn("admin", self.fake.get(edge_key("203.0.113.100")), "and still the administrator's record")

    def test_a_permanent_block_replaces_a_temporary_one_and_temporary_blocks_still_refresh(self):
        store.block("203.0.113.101", "tarpit", source="tarpit", ttl_seconds=30, conn=self.fake)
        store.block("203.0.113.101", "tarpit again", source="tarpit", ttl_seconds=600, conn=self.fake)
        self.assertGreater(self.fake.ttl(edge_key("203.0.113.101")), 30, "a temporary block refreshes a temporary one")

        store.block("203.0.113.101", "admin", source="admin_ui", conn=self.fake)
        self.assertEqual(self.fake.ttl(edge_key("203.0.113.101")), -1)

    def test_migration_keeps_a_permanent_block_when_the_same_address_has_a_legacy_tarpit_key(self):
        self.fake.sadd("default:blocklist", "203.0.113.102")
        self.fake.setex("default:blocklist:203.0.113.102", 600, "tarpit reason")

        store.migrate_legacy(conn=self.fake)

        self.assertEqual(self.fake.ttl(edge_key("203.0.113.102")), -1)


class LegacyTarpitTtlEdges(unittest.TestCase):
    def test_a_key_with_under_a_second_left_keeps_a_bounded_expiry(self):
        fake = FakeBlocklistRedis()
        fake.setex("default:blocklist:203.0.113.110", 60, "r")
        fake.expires["default:blocklist:203.0.113.110"] = time.monotonic() + 0.4  # TTL reads as 0

        store.migrate_legacy(conn=fake)

        self.assertEqual(fake.exists(edge_key("203.0.113.110")), 1)
        self.assertGreater(fake.ttl(edge_key("203.0.113.110")), -1, "bounded, not permanent")

    def test_a_key_that_expired_after_it_was_listed_is_skipped_not_made_permanent(self):
        class Vanishing(FakeBlocklistRedis):
            def ttl(self, key):
                return -2 if key.endswith("203.0.113.111") else super().ttl(key)

        fake = Vanishing()
        fake.setex("default:blocklist:203.0.113.111", 60, "r")

        store.migrate_legacy(conn=fake)

        self.assertEqual(fake.exists(edge_key("203.0.113.111")), 0)

    def test_a_legacy_key_with_no_expiry_migrates_as_permanent(self):
        fake = FakeBlocklistRedis()
        fake.set("default:blocklist:203.0.113.112", "r")

        store.migrate_legacy(conn=fake)

        self.assertEqual(fake.ttl(edge_key("203.0.113.112")), -1)


class UnblockClearsLegacyDatabases(unittest.TestCase):
    def test_unblock_clears_the_old_set_in_the_default_database_so_migration_cannot_bring_it_back(self):
        main, default_db = FakeBlocklistRedis(), FakeBlocklistRedis()
        default_db.sadd("default:blocklist", "203.0.113.120")  # an old admin block, not yet migrated

        self.assertTrue(store.unblock("203.0.113.120", conn=main, legacy_conns=(default_db,)))
        store.migrate_legacy(conn=main, extra_conns=(default_db,))

        self.assertEqual(default_db.smembers("default:blocklist"), set())
        self.assertEqual(main.exists(edge_key("203.0.113.120")), 0, "the lifted block was not resurrected")

    def test_a_missing_legacy_connection_is_ignored(self):
        main = FakeBlocklistRedis()
        main.set(edge_key("203.0.113.121"), "{}")

        self.assertTrue(store.unblock("203.0.113.121", conn=main, legacy_conns=(None,)))


class Listing(unittest.TestCase):
    def test_list_and_counts_see_permanent_and_temporary_blocks(self):
        fake = FakeBlocklistRedis()
        store.block("203.0.113.80", "x", source="admin_ui", conn=fake)
        store.block("203.0.113.81", "x", source="tarpit", ttl_seconds=300, conn=fake)
        fake.set("default:throttle:ip:203.0.113.82", "{}")  # other contracts are not counted
        self.assertEqual(store.list_blocked(fake), ["203.0.113.80", "203.0.113.81"])
        self.assertEqual(store.counts(fake), {"blocked": 2, "temporary": 1})


class LegacyMigration(unittest.TestCase):
    def test_legacy_sets_and_tarpit_keys_become_real_blocks(self):
        main, default_db = FakeBlocklistRedis(), FakeBlocklistRedis()
        default_db.sadd("default:blocklist", "203.0.113.90")  # the admin UI's old set, in the default database
        main.sadd("default:blocklist", "203.0.113.91")  # the webhook's old set
        main.setex("default:blocklist:203.0.113.92", 600, "bot reason")  # the tarpit's old key
        main.set("default:blocklist:ip:203.0.113.93", "{}")  # already correct: untouched

        moved = store.migrate_legacy(conn=main, extra_conns=(default_db,))

        self.assertEqual(moved, 3)
        for ip in ("90", "91", "92", "93"):
            self.assertEqual(main.exists(edge_key(f"203.0.113.{ip}")), 1)
        self.assertGreater(main.ttl(edge_key("203.0.113.92")), 0, "a legacy TTL is kept")
        self.assertEqual(main.ttl(edge_key("203.0.113.90")), -1)
        self.assertEqual(default_db.smembers("default:blocklist"), set())
        self.assertEqual(main.smembers("default:blocklist"), set())
        self.assertEqual(main.exists("default:blocklist:203.0.113.92"), 0)
        self.assertEqual(store.migrate_legacy(conn=main, extra_conns=(default_db,)), 0, "idempotent")

    def test_a_bad_legacy_member_is_left_alone_and_does_not_stop_the_rest(self):
        fake = FakeBlocklistRedis()
        fake.sadd("default:blocklist", "garbage")
        fake.sadd("default:blocklist", "203.0.113.94")
        self.assertEqual(store.migrate_legacy(conn=fake), 1)
        self.assertEqual(fake.smembers("default:blocklist"), {"garbage"})

    def test_a_redis_error_during_migration_is_contained(self):
        fake = FakeBlocklistRedis()
        fake.fail_with = RedisError("down")
        self.assertEqual(store.migrate_legacy(conn=fake), 0)


if __name__ == "__main__":
    unittest.main()
