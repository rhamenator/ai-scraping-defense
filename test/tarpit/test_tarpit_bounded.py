"""The Python Markov fallback and the tarpit handler must terminate and stay responsive (#1908)."""

import asyncio
import random
import time
import unittest
from unittest.mock import MagicMock, patch

import httpx
import psycopg2

from src.tarpit import markov_generator as mg
from src.tarpit import tarpit_api
from test.tarpit.test_tarpit_api import TestTarpitAPIComprehensive


# The shared API test base patches these names for the whole module, so keep the real objects from before that.
REAL_ASYNC_CLIENT = httpx.AsyncClient
REAL_GENERATOR = tarpit_api.generate_dynamic_tarpit_page


class MarkovBoundsTests(unittest.TestCase):
    def setUp(self):
        conn = MagicMock()
        patcher = patch.object(mg, "_get_db_connection", return_value=(conn, MagicMock()))
        patcher.start()
        self.addCleanup(patcher.stop)
        release = patch.object(mg, "_release_db_connection")
        release.start()
        self.addCleanup(release.stop)
        self.rng = random.Random(7)  # nosec B311 - deterministic test data

    def test_an_empty_model_returns_static_content_after_a_few_lookups(self):
        with patch.object(mg, "get_next_word_from_db", return_value=None) as lookup:
            started = time.monotonic()
            content = mg.generate_markov_text_from_db(5, rng=self.rng)
        self.assertEqual(content, mg.MARKOV_UNAVAILABLE_HTML)
        self.assertEqual(lookup.call_count, mg.MARKOV_MAX_EMPTY_LOOKUPS)
        self.assertLess(time.monotonic() - started, 1.0)

    def test_a_disconnected_database_terminates_through_the_real_lookup(self):
        cursor = MagicMock()
        cursor.execute.side_effect = psycopg2.OperationalError("connection lost")
        with patch.object(mg, "_get_db_connection", return_value=(MagicMock(), cursor)), patch.object(
            mg, "_db_pool", MagicMock()
        ):
            started = time.monotonic()
            content = mg.generate_markov_text_from_db(5, rng=self.rng)
        self.assertEqual(content, mg.MARKOV_UNAVAILABLE_HTML)
        self.assertLess(time.monotonic() - started, 1.0)
        # one failed lookup per allowed attempt, no more
        self.assertEqual(cursor.execute.call_count, mg.MARKOV_MAX_EMPTY_LOOKUPS)

    def test_a_chain_that_dies_late_keeps_the_text_generated_so_far(self):
        words = iter(["alpha", "beta", "gamma", "delta"])

        def lookup(*_args, **_kwargs):
            return next(words, None)

        with patch.object(mg, "get_next_word_from_db", side_effect=lookup), patch.object(
            mg, "get_word_id", return_value=2
        ), patch.object(self.rng, "randint", return_value=30):
            content = mg.generate_markov_text_from_db(2, rng=self.rng)
        self.assertIn("alpha beta gamma delta", content)
        self.assertNotEqual(content, mg.MARKOV_UNAVAILABLE_HTML)

    def test_the_wall_clock_deadline_ends_generation_with_partial_text(self):
        clock = iter([0.0, 0.0, 0.0, 99.0, 99.0, 99.0, 99.0])
        with patch.object(mg.time, "monotonic", side_effect=lambda: next(clock)), patch.object(
            mg, "get_next_word_from_db", return_value="word"
        ), patch.object(mg, "get_word_id", return_value=2):
            content = mg.generate_markov_text_from_db(5, rng=self.rng)
        self.assertIn("<p>word", content)

    def test_the_lookup_budget_ends_generation_even_if_the_empty_streak_cap_is_removed(self):
        with patch.object(mg, "MARKOV_MAX_EMPTY_LOOKUPS", 10**9), patch.object(
            self.rng, "randint", return_value=15
        ), patch.object(mg, "get_next_word_from_db", return_value=None) as lookup:
            content = mg.generate_markov_text_from_db(1, rng=self.rng)
        self.assertEqual(content, mg.MARKOV_UNAVAILABLE_HTML)
        self.assertEqual(lookup.call_count, 15 * 4)

    def test_normal_generation_is_unchanged(self):
        words = iter(f"w{i}" for i in range(1000))
        with patch.object(mg, "get_next_word_from_db", side_effect=lambda *a, **k: next(words)), patch.object(
            mg, "get_word_id", return_value=2
        ), patch.object(self.rng, "randint", return_value=15):
            content = mg.generate_markov_text_from_db(1, rng=self.rng)
        self.assertEqual(content.count("w"), 15)

    def test_the_pool_is_thread_safe_and_has_a_statement_timeout(self):
        with patch.object(mg, "_db_pool", None), patch.object(
            mg, "_get_pg_password", return_value="x"
        ), patch.object(mg.pool, "ThreadedConnectionPool") as threaded:
            mg._get_db_pool()
        threaded.assert_called_once()
        self.assertIn("statement_timeout", threaded.call_args.kwargs["options"])
        self.assertFalse(hasattr(mg.pool, "SimpleConnectionPool") and mg.pool.SimpleConnectionPool is threaded)


class PoolOwnershipTests(unittest.TestCase):
    """A database error replaces the global pool while other threads still hold connections (#1908 review)."""

    def test_a_connection_goes_back_to_the_pool_that_issued_it(self):
        old_pool, new_pool = MagicMock(), MagicMock()
        connection = MagicMock()
        old_pool.getconn.return_value = connection
        with patch.object(mg, "_db_pool", old_pool):
            conn, cursor = mg._get_db_connection()
        self.assertIs(conn, connection)
        with patch.object(mg, "_db_pool", new_pool):  # the global was replaced meanwhile
            mg._release_db_connection(conn, cursor)
        old_pool.putconn.assert_called_once_with(connection)
        new_pool.putconn.assert_not_called()
        self.assertNotIn(connection, mg._connection_owners)

    def test_releasing_an_unknown_connection_does_nothing(self):
        pool = MagicMock()
        with patch.object(mg, "_db_pool", pool):
            mg._release_db_connection(MagicMock(), None)
        pool.putconn.assert_not_called()

    def test_only_the_pool_that_failed_is_invalidated(self):
        failed, current = MagicMock(), MagicMock()
        with patch.object(mg, "_db_pool", current):
            mg._invalidate_db_pool(failed)
            self.assertIs(mg._db_pool, current)
            mg._invalidate_db_pool(current)
            self.assertIsNone(mg._db_pool)

    def test_a_failing_query_invalidates_its_own_pool_not_a_newer_one(self):
        failed_pool, newer_pool = MagicMock(), MagicMock()
        connection = MagicMock()
        failed_pool.getconn.return_value = connection
        connection.cursor.return_value.execute.side_effect = psycopg2.OperationalError("timeout")
        with patch.object(mg, "_db_pool", failed_pool):
            conn, cursor = mg._get_db_connection()
        with patch.object(mg, "_get_db_connection", return_value=(conn, cursor)), patch.object(
            mg, "_db_pool", newer_pool
        ):
            self.assertIsNone(mg.get_next_word_from_db(1, 1, rng=random.Random(1)))  # nosec B311
            self.assertIs(mg._db_pool, newer_pool)


class HandlerResponsivenessTests(unittest.IsolatedAsyncioTestCase):
    """Run the real handler in one event loop, so a blocked loop would be visible."""

    def setUp(self):
        base = TestTarpitAPIComprehensive("test_tarpit_handler_normal_flow")
        base.setUp()
        self.addCleanup(base.tearDown)
        self.base = base
        base.mock_redis_hops.pipeline.return_value.execute.return_value = [1, True]
        # The tarpit streams its answer with deliberate delays; remove them so timings reflect generation only.
        for name in ("MIN_STREAM_DELAY_SEC", "MAX_STREAM_DELAY_SEC"):
            patcher = patch.object(tarpit_api, name, 0.0)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _client(self):
        return REAL_ASYNC_CLIENT(transport=httpx.ASGITransport(app=tarpit_api.app), base_url="http://test")

    async def test_a_slow_generator_does_not_block_other_requests(self):
        def slow(_rng):
            time.sleep(0.6)
            return "<html>slow page</html>"

        async def measure_health(client):
            await asyncio.sleep(0.1)  # let the slow request start first
            started = time.monotonic()
            response = await client.get("/health")
            return time.monotonic() - started, response

        with patch.object(tarpit_api, "generate_dynamic_tarpit_page", side_effect=slow):
            async with self._client() as client:
                slow_request = asyncio.create_task(client.get("/tarpit/some/path", headers={"User-Agent": "Bot"}))
                elapsed, health = await measure_health(client)
                page = await slow_request
        self.assertLess(elapsed, 0.4, "the health check waited for the generator, so the loop was blocked")
        self.assertIn(health.status_code, (200, 503))
        self.assertEqual(page.status_code, 200)
        self.assertIn("slow page", page.text)

    async def test_a_generator_that_exceeds_the_deadline_gets_static_content(self):
        def stuck(_rng):
            time.sleep(1.0)
            return "<html>too late</html>"

        with patch.object(tarpit_api, "TARPIT_GENERATION_TIMEOUT_SECONDS", 0.3), patch.object(
            tarpit_api, "generate_dynamic_tarpit_page", side_effect=stuck
        ):
            async with self._client() as client:
                started = time.monotonic()
                response = await client.get("/tarpit/some/path", headers={"User-Agent": "Bot"})
                elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.8)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Service temporarily unavailable", response.text)
        self.assertNotIn("too late", response.text)

    def test_the_api_uses_the_wrapper_so_the_rust_backend_is_called_correctly(self):
        """tarpit_rs's function takes no RNG; calling it directly with one raised TypeError."""
        self.assertEqual(REAL_GENERATOR.__module__, "src.tarpit.markov_generator")
        self.assertEqual(REAL_GENERATOR.__name__, "generate_dynamic_tarpit_page")
        # Patch through the function's own globals: other tests reload the module, so a module reference can be stale.
        with patch.dict(
            REAL_GENERATOR.__globals__,
            {
                "RUST_ENABLED": True,
                "ENABLE_TARPIT_LLM_GENERATOR": False,
                "rs_generate_dynamic_tarpit_page": lambda: "<html>from rust</html>",
            },
        ):
            self.assertEqual(
                REAL_GENERATOR(random.Random(1)),  # nosec B311
                "<html>from rust</html>",
            )

    def test_the_api_never_imports_the_raw_extension_function(self):
        source = open(tarpit_api.__file__, encoding="utf-8").read()
        self.assertNotIn("from tarpit_rs import", source)

    def test_health_reports_which_implementation_loaded(self):
        self.assertIn(tarpit_api.GENERATOR_IMPLEMENTATION, {"rust", "python"})
        response = self.base.client.get("/health")
        self.assertIn(response.status_code, (200, 503))
        self.assertEqual(response.json().get("generator_implementation"), tarpit_api.GENERATOR_IMPLEMENTATION)
