"""Block log search, range filter, paging and CSV export (#1951)."""

import csv
import datetime
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import bcrypt
import pyotp
from fastapi.testclient import TestClient

from src.admin_ui import admin_ui, auth, block_log, blocklist

NOW = datetime.datetime(2026, 11, 22, 12, 0, tzinfo=datetime.timezone.utc)


def _line(minutes_ago: int, ip: str, reason: str) -> str:
    stamp = (NOW - datetime.timedelta(minutes=minutes_ago)).isoformat()
    return json.dumps({"timestamp": stamp, "ip_address": ip, "reason": reason}) + "\n"


class BlockLogTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile("w", suffix=".log", delete=False)
        self.addCleanup(os.unlink, handle.name)
        self.path = handle.name
        lines = [
            # the log is append-only, so it is oldest first on disk
            _line(60 * 24 * 40, "192.0.2.1", "old block"),
            _line(60 * 30, "203.0.113.9", "rate limit"),
            _line(90, "198.51.100.4", "honeypot hit"),
            _line(5, "203.0.113.7", "High Combined Score (0.95)"),
            "not json\n",
            json.dumps({"timestamp": "bad", "ip_address": "1.1.1.1"}) + "\n",
            json.dumps({"timestamp": NOW.isoformat(), "ip_address": "not-an-ip"}) + "\n",
        ]
        handle.writelines(lines)
        handle.close()

    def _q(self, **kwargs):
        return block_log.query_events(self.path, now=NOW, **kwargs)

    def test_newest_first_and_malformed_lines_are_skipped(self):
        result = self._q()
        self.assertEqual([e["ip"] for e in result.events], ["203.0.113.7", "198.51.100.4", "203.0.113.9", "192.0.2.1"])
        self.assertEqual(result.total, 4)

    def test_search_matches_address_and_reason_case_insensitively(self):
        self.assertEqual([e["ip"] for e in self._q(query="203.0.113").events], ["203.0.113.7", "203.0.113.9"])
        self.assertEqual([e["ip"] for e in self._q(query="HONEYPOT").events], ["198.51.100.4"])
        self.assertEqual(self._q(query="nothing matches this").total, 0)

    def test_time_range_filters(self):
        self.assertEqual(self._q(range_key="1h").total, 1)
        self.assertEqual(self._q(range_key="24h").total, 2)
        self.assertEqual(self._q(range_key="7d").total, 3)
        self.assertEqual(self._q(range_key="30d").total, 3)
        self.assertEqual(self._q(range_key="all").total, 4)

    def test_paging_clamps_and_reports_pages(self):
        first = self._q(page=1, page_size=3)
        self.assertEqual((first.pages, len(first.events), first.page), (2, 3, 1))
        second = self._q(page=2, page_size=3)
        self.assertEqual([e["ip"] for e in second.events], ["192.0.2.1"])
        beyond = self._q(page=99, page_size=3)
        self.assertEqual(beyond.page, 2)
        huge = self._q(page_size=10_000)
        self.assertEqual(huge.page_size, block_log.MAX_PAGE_SIZE)
        self.assertEqual(self._q(page=-4, page_size=0).page_size, 1)

    def test_only_the_newest_lines_are_scanned_when_the_log_is_huge(self):
        with patch.object(block_log, "MAX_SCAN_LINES", 2):
            result = self._q()
        # last two lines are malformed, so nothing valid remains, and the cut is reported
        self.assertTrue(result.truncated)
        self.assertEqual(result.total, 0)

    def test_every_reachable_page_number_is_accepted(self):
        """With a page size of 1 the last page can exceed 10,000; the Older link must never lead to a rejected page."""
        self.assertEqual(block_log.MAX_PAGE, block_log.MAX_SCAN_LINES)
        result = self._q(page=3, page_size=1)
        self.assertEqual((result.pages, result.page), (4, 3))

    def test_missing_log_file_is_an_empty_result(self):
        result = block_log.query_events("/nonexistent/block.log", now=NOW)
        self.assertEqual((result.total, result.events, result.pages), (0, [], 1))

    def test_csv_neutralises_formula_injection_and_quotes_awkward_values(self):
        for text in ("=1+1", "+cmd", "-2+3", "@SUM(A1)", "\tTab", "\rCR"):
            self.assertTrue(block_log.csv_cell(text).startswith("'"), text)
        self.assertEqual(block_log.csv_cell("plain"), "plain")
        self.assertEqual(block_log.csv_cell(None), "")
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(_line(1, "203.0.113.50", '=HYPERLINK("http://evil","x"), line\nbreak'))
        rows = list(csv.reader(io.StringIO(block_log.export_csv(self.path, now=NOW))))
        self.assertEqual(rows[0], ["timestamp", "ip", "reason"])
        self.assertEqual(rows[1][1], "203.0.113.50")
        self.assertEqual(rows[1][2], "'=HYPERLINK(\"http://evil\",\"x\"), line\nbreak")

    def test_export_reflects_the_filter_and_is_bounded(self):
        rows = list(csv.reader(io.StringIO(block_log.export_csv(self.path, "203.0.113", "7d", now=NOW))))
        self.assertEqual([r[1] for r in rows[1:]], ["203.0.113.7", "203.0.113.9"])
        with patch.object(block_log, "MAX_EXPORT_ROWS", 1):
            rows = list(csv.reader(io.StringIO(block_log.export_csv(self.path, now=NOW))))
        self.assertEqual(len(rows), 2)

    def test_unknown_range_is_rejected(self):
        with self.assertRaises(ValueError):
            self._q(range_key="forever")


class LogsRouteTests(unittest.TestCase):
    def setUp(self):
        os.environ["ADMIN_UI_USERNAME"] = "admin"
        os.environ["ADMIN_UI_PASSWORD_HASH"] = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
        os.environ["ADMIN_UI_ROLE"] = "admin"
        os.environ["ADMIN_UI_2FA_SECRET"] = pyotp.random_base32()
        auth.ADMIN_UI_ROLE = "admin"
        patcher = patch("src.admin_ui.auth.get_redis_connection", return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)
        handle = tempfile.NamedTemporaryFile("w", suffix=".log", delete=False)
        self.addCleanup(os.unlink, handle.name)
        now = datetime.datetime.now(datetime.timezone.utc)
        for index in range(120):
            stamp = (now - datetime.timedelta(minutes=index)).isoformat()
            handle.write(json.dumps({"timestamp": stamp, "ip_address": f"203.0.113.{index % 250}", "reason": "scrape"}) + "\n")
        handle.write(json.dumps({"timestamp": now.isoformat(), "ip_address": "198.51.100.77", "reason": "=cmd|' /C calc'!A0"}) + "\n")
        handle.close()
        bl = patch.object(blocklist, "BLOCK_LOG_FILE", handle.name)
        bl.start()
        self.addCleanup(bl.stop)
        self.client = TestClient(admin_ui.app)
        self.auth = ("admin", "testpass")

    def _headers(self):
        return {"X-2FA-Code": pyotp.TOTP(os.environ["ADMIN_UI_2FA_SECRET"]).now()}

    def _get(self, url):
        return self.client.get(url, auth=self.auth, headers=self._headers())

    def test_logs_page_pages_filters_and_links(self):
        page = self._get("/logs?page_size=50")
        self.assertEqual(page.status_code, 200)
        self.assertIn("121 matching events", page.text)
        self.assertIn("page 1 of 3", page.text)
        self.assertIn('id="log-next"', page.text)
        self.assertNotIn('id="log-prev"', page.text)
        last = self._get("/logs?page=3&page_size=50")
        self.assertIn('id="log-prev"', last.text)
        self.assertNotIn('id="log-next"', last.text)
        found = self._get("/logs?q=198.51.100.77")
        self.assertIn("1 matching event;", found.text)
        self.assertIn('href="/logs/export.csv?q=198.51.100.77&amp;range=all"', found.text)

    def test_query_parameters_are_validated_server_side(self):
        for bad in ("page=0", "page=abc", "page_size=0", "page_size=201", "range=forever", "q=" + "x" * 101, "page=100001"):
            self.assertEqual(self._get("/logs?" + bad).status_code, 422, bad)
        # the export takes the filter only (it is not paged), so paging parameters are ignored there
        self.assertEqual(self._get("/logs/export.csv?page=0").status_code, 200)
        self.assertEqual(self._get("/logs/export.csv?range=forever").status_code, 422)
        self.assertEqual(self._get("/logs/export.csv?q=" + "x" * 101).status_code, 422)

    def test_search_text_is_escaped_in_the_page(self):
        page = self._get("/logs?q=%22%3E%3Cscript%3Ealert(1)%3C/script%3E")
        self.assertNotIn("<script>alert(1)</script>", page.text)

    def test_export_is_a_csv_attachment_with_neutralised_cells(self):
        response = self._get("/logs/export.csv?q=198.51.100.77&range=24h")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/csv"))
        self.assertIn('attachment; filename="block-log-24h.csv"', response.headers["content-disposition"])
        rows = list(csv.reader(io.StringIO(response.text)))
        self.assertEqual(rows[0], ["timestamp", "ip", "reason"])
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[1][2].startswith("'="))

    def test_logs_and_export_require_authentication(self):
        self.assertEqual(self.client.get("/logs").status_code, 401)
        self.assertEqual(self.client.get("/logs/export.csv").status_code, 401)
