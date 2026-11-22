"""Integrity, bounds and staged activation for downloaded WAF rules (#1907)."""

import hashlib
import io
import os
import socket
import subprocess  # nosec B404
import tarfile
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from src.util import rules_fetcher, waf_manager
from src.util.rules_fetcher import config, crs, fetcher
from test.util.test_rules_fetcher import MockResponse

GOOD_RULES = "# custom\nSecRule REQUEST_URI \"@contains /evil\" \\\n    \"id:1001,phase:1,deny\"\nSecMarker END\n"
PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))]


def sha(data) -> str:
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def crs_tar(rules=None, extra=None, setup=b"# setup") -> bytes:
    rules = rules if rules is not None else {"rules/REQUEST-901.conf": b'SecAction "id:1,phase:1,pass"\n'}
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tf:
        for name, data in {"crs-setup.conf.example": setup, **rules, **(extra or {})}.items():
            info = tarfile.TarInfo("crs-1.0/" + name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        dns = patch("src.shared.ssrf_protection.socket.getaddrinfo", return_value=PUBLIC)
        dns.start()
        self.addCleanup(dns.stop)
        http = patch("src.util.rules_fetcher.download.requests.get")
        self.get = http.start()
        self.addCleanup(http.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = self.tmp.name

    def config(self, **values):
        for name, value in values.items():
            patcher = patch.object(config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def serve(self, body, status=200, headers=None):
        response = MockResponse(body, status)
        response.headers = headers or {}
        self.get.return_value = response
        return response

    def live(self, rule="SecAction \"id:99,phase:1,pass\"\n", setup="# old setup"):
        os.makedirs(os.path.join(self.dest, "rules"))
        with open(os.path.join(self.dest, "rules", "old.conf"), "w") as f:
            f.write(rule)
        with open(os.path.join(self.dest, "crs-setup.conf"), "w") as f:
            f.write(setup)

    def read(self, *parts):
        with open(os.path.join(self.dest, *parts)) as f:
            return f.read()

    def assertLiveUntouched(self):
        self.assertEqual(self.read("rules", "old.conf"), "SecAction \"id:99,phase:1,pass\"\n")
        self.assertEqual(self.read("crs-setup.conf"), "# old setup")
        self.assertFalse(os.path.exists(os.path.join(self.dest, "rules.previous")))
        self.assertEqual([n for n in os.listdir(self.dest) if n.startswith(".crs-staging")], [], "staging left behind")


class FetchRulesIntegrity(Base):
    def test_a_download_matching_the_pinned_digest_is_accepted(self):
        self.serve(GOOD_RULES)
        self.assertEqual(rules_fetcher.fetch_rules("https://example.com/r", expected_sha256=sha(GOOD_RULES)), GOOD_RULES)

    def test_a_wrong_digest_is_refused(self):
        self.serve(GOOD_RULES)
        self.assertEqual(rules_fetcher.fetch_rules("https://example.com/r", expected_sha256=sha("other")), "")

    def test_the_digest_comes_from_configuration_and_a_malformed_pin_fails_closed(self):
        self.serve(GOOD_RULES)
        self.config(RULES_SHA256=sha(GOOD_RULES))
        self.assertEqual(rules_fetcher.fetch_rules("https://example.com/r"), GOOD_RULES)
        self.config(RULES_SHA256="not-a-digest")
        self.assertEqual(rules_fetcher.fetch_rules("https://example.com/r"), "")

    def test_requiring_a_digest_refuses_an_unpinned_download_and_otherwise_it_only_warns(self):
        self.serve(GOOD_RULES)
        self.assertEqual(rules_fetcher.fetch_rules("https://example.com/r"), GOOD_RULES)
        self.config(RULES_REQUIRE_DIGEST=True)
        self.assertEqual(rules_fetcher.fetch_rules("https://example.com/r"), "")

    def test_an_oversized_body_is_refused_while_streaming_and_by_content_length(self):
        self.config(RULES_MAX_BYTES=1000)
        self.serve("SecMarker A\n" * 200)
        self.assertEqual(rules_fetcher.fetch_rules("https://example.com/r"), "")
        self.serve(GOOD_RULES, headers={"Content-Length": "999999"})
        self.assertEqual(rules_fetcher.fetch_rules("https://example.com/r"), "")

    def test_the_body_is_never_read_past_the_limit(self):
        self.config(RULES_MAX_BYTES=100)
        read = []

        class Endless(MockResponse):
            def iter_content(self, chunk_size=65536):
                while True:
                    read.append(chunk_size)
                    yield b"SecMarker X\n" * 20

        self.get.return_value = Endless("x")
        self.assertEqual(rules_fetcher.fetch_rules("https://example.com/r"), "")
        self.assertLess(len(read), 5)

    def test_a_redirect_is_refused_with_a_clear_reason(self):
        self.serve("", status=302)
        with self.assertLogs("src.util.rules_fetcher.fetcher", "ERROR") as logs:
            self.assertEqual(rules_fetcher.fetch_rules("https://example.com/r"), "")
        self.assertIn("redirects are not followed", "".join(logs.output))

    def test_content_that_is_not_modsecurity_or_uses_dangerous_directives_is_refused(self):
        bad = {
            "html": "<html><body>404 Not Found</body></html>",
            "include": "Include /etc/passwd\n",
            "script": 'SecRuleScript /tmp/x.lua "phase:1"\n',
            "remote": "SecRemoteRules key https://evil.example/rules\n",
            "inspect": 'SecRule FILES_TMPNAMES "@inspectFile /bin/sh" "id:7,phase:2,deny"\n',
            "exec": 'SecAction "id:8,phase:1,exec:/bin/sh"\n',
            "path": "SecAuditLog /etc/cron.d/x\n",
            "empty": "# only a comment\n",
            "nul": "SecMarker A\x00\n",
        }
        for name, body in bad.items():
            with self.subTest(name=name):
                self.serve(body)
                self.assertEqual(rules_fetcher.fetch_rules("https://example.com/r"), "")

    def test_continuation_lines_and_comments_are_valid(self):
        self.serve(GOOD_RULES)
        self.assertEqual(rules_fetcher.fetch_rules("https://example.com/r"), GOOD_RULES)


class CrsInstall(Base):
    def install(self, archive, url="https://example.com/crs.tar.gz", **kwargs):
        self.serve(archive)
        return rules_fetcher.download_and_extract_crs(url, self.dest, **kwargs)

    def test_a_known_good_archive_with_the_right_digest_installs_and_keeps_the_previous_rules(self):
        self.live()
        archive = crs_tar()
        self.assertTrue(self.install(archive, expected_sha256=sha(archive)))
        self.assertIn("id:1", self.read("rules", "REQUEST-901.conf"))
        self.assertEqual(self.read("crs-setup.conf"), "# setup")
        self.assertEqual(self.read("rules.previous", "old.conf"), "SecAction \"id:99,phase:1,pass\"\n")
        self.assertEqual([n for n in os.listdir(self.dest) if n.startswith(".crs-staging")], [])

    def test_a_wrong_digest_installs_nothing(self):
        self.live()
        self.assertFalse(self.install(crs_tar(), expected_sha256=sha(b"x")))
        self.assertLiveUntouched()

    def test_the_digest_can_come_from_configuration(self):
        archive = crs_tar()
        self.config(CRS_SHA256=sha(archive))
        self.assertTrue(self.install(archive))
        self.config(CRS_SHA256=sha(b"different"))
        self.live_backup = None
        self.assertFalse(self.install(archive))

    def test_a_decompression_bomb_stays_within_the_budget_and_never_replaces_live_files(self):
        self.live()
        self.config(CRS_MAX_EXTRACTED_BYTES=1024 * 1024)
        bomb = crs_tar(rules={"rules/big.conf": b"SecMarker A\n" + b"#" * (20 * 1024 * 1024)})
        self.assertLess(len(bomb), 100 * 1024)
        self.assertFalse(self.install(bomb))
        self.assertLiveUntouched()

    def test_the_expansion_ratio_is_enforced_independently_of_the_absolute_limit(self):
        self.live()
        self.config(CRS_MAX_EXPANSION_RATIO=10)
        bomb = crs_tar(rules={"rules/big.conf": b"SecMarker A\n" + b"#" * (2 * 1024 * 1024)})
        self.assertFalse(self.install(bomb))
        self.assertLiveUntouched()

    def test_a_single_oversized_member_is_refused_before_it_is_read(self):
        self.live()
        self.config(CRS_MAX_FILE_BYTES=1000)
        self.assertFalse(self.install(crs_tar(rules={"rules/big.conf": b"SecMarker A\n" + b"#" * 5000})))
        self.assertLiveUntouched()

    def test_too_many_members_are_refused(self):
        self.live()
        self.config(CRS_MAX_MEMBERS=10)
        many = {f"rules/r{i}.conf": b"SecMarker A\n" for i in range(50)}
        self.assertFalse(self.install(crs_tar(rules=many)))
        self.assertLiveUntouched()

    def test_a_zip_bomb_is_refused_too(self):
        self.live()
        self.config(CRS_MAX_EXTRACTED_BYTES=1024 * 1024)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("crs-1.0/crs-setup.conf.example", "# s")
            zf.writestr("crs-1.0/rules/big.conf", "SecMarker A\n" + "#" * (20 * 1024 * 1024))
        self.assertFalse(self.install(buffer.getvalue(), url="https://example.com/crs.zip"))
        self.assertLiveUntouched()

    def test_rules_that_fail_validation_never_replace_the_live_files(self):
        self.live()
        for name, body in {
            "script": b'SecRuleScript /x.lua "phase:1"\n',
            "inspect": b'SecRule FILES "@inspectFile /bin/sh" "id:5,phase:2,deny"\n',
            "binary": b"\xff\xfe\x00",
        }.items():
            with self.subTest(name=name):
                self.assertFalse(self.install(crs_tar(rules={"rules/bad.conf": body})))
                self.assertLiveUntouched()

    def test_an_archive_without_rules_or_setup_is_refused(self):
        self.live()
        self.assertFalse(self.install(crs_tar(rules={})))
        self.assertLiveUntouched()

    def test_only_the_rules_and_setup_are_extracted(self):
        archive = crs_tar(extra={"util/run.sh": b"#!/bin/sh\nrm -rf /\n", "tests/x.yaml": b"a: b\n", "rules/notes.exe": b"MZ"})
        self.assertTrue(self.install(archive))
        self.assertEqual(sorted(os.listdir(self.dest)), ["crs-setup.conf", "rules"])
        self.assertEqual(os.listdir(os.path.join(self.dest, "rules")), ["REQUEST-901.conf"])

    def test_the_source_must_be_https_and_on_the_allowlist_before_anything_is_requested(self):
        self.get.reset_mock()
        self.assertFalse(rules_fetcher.download_and_extract_crs("http://example.com/crs.tar.gz", self.dest))
        self.assertFalse(
            rules_fetcher.download_and_extract_crs("https://elsewhere.example/crs.tar.gz", self.dest, allowed_domains=["example.com"])
        )
        self.get.assert_not_called()

    def test_a_redirect_from_the_download_url_is_refused(self):
        self.serve(b"", status=302)
        self.assertFalse(rules_fetcher.download_and_extract_crs("https://example.com/crs.tar.gz", self.dest))
        self.assertEqual(os.listdir(self.dest), [])

    def test_an_oversized_download_is_refused(self):
        self.config(CRS_MAX_DOWNLOAD_BYTES=100)
        self.assertFalse(self.install(crs_tar()))
        self.assertEqual(os.listdir(self.dest), [])

    def test_rollback_restores_the_previous_generation(self):
        self.live()
        self.assertTrue(self.install(crs_tar()))
        self.assertTrue(crs.rollback_crs(self.dest))
        self.assertEqual(self.read("rules", "old.conf"), "SecAction \"id:99,phase:1,pass\"\n")
        self.assertEqual(self.read("crs-setup.conf"), "# old setup")
        self.assertFalse(crs.rollback_crs(self.dest), "nothing left to restore")

    def test_a_failed_reload_after_install_rolls_the_rules_back(self):
        self.live()
        self.serve(crs_tar())
        calls = []

        def reload(cmd, **kw):
            calls.append(cmd)
            if len(calls) == 1:
                raise subprocess.CalledProcessError(1, cmd)

        with (
            patch.object(fetcher, "CRS_DOWNLOAD_URL", "https://example.com/crs.tar.gz"),
            patch.object(fetcher, "MODSEC_DIR", self.dest),
            patch.object(fetcher, "ALLOWED_RULES_DOMAINS", []),
            patch("src.util.rules_fetcher.fetcher.subprocess.run", side_effect=reload),
        ):
            self.assertFalse(fetcher._run_as_script())
        self.assertEqual(len(calls), 2, "reloaded again after restoring")
        self.assertEqual(self.read("rules", "old.conf"), "SecAction \"id:99,phase:1,pass\"\n")
        self.assertFalse(os.path.exists(os.path.join(self.dest, "rules", "REQUEST-901.conf")))


class CustomRulesActivation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "custom.rules")
        for target in (
            patch.object(waf_manager, "WAF_RULES_PATH", self.path),
            patch.object(waf_manager, "ENABLE_WAF", True),
        ):
            target.start()
            self.addCleanup(target.stop)

    def read(self, path=None):
        with open(path or self.path) as f:
            return f.read()

    def test_success_replaces_the_file_atomically_and_keeps_the_previous_one(self):
        with open(self.path, "w") as f:
            f.write("old\n")
        with patch("src.util.waf_manager.subprocess.run") as run:
            self.assertTrue(waf_manager.reload_waf_rules(["new"]))
        run.assert_called_once()
        self.assertEqual(self.read(), "new\n")
        self.assertEqual(self.read(self.path + ".previous"), "old\n")
        self.assertFalse(os.path.exists(self.path + ".new"))

    def test_a_failed_reload_restores_the_previous_rules(self):
        with open(self.path, "w") as f:
            f.write("old\n")
        calls = []

        def run(cmd, **kw):
            calls.append(cmd)
            if len(calls) == 1:
                raise subprocess.CalledProcessError(1, cmd)

        with patch("src.util.waf_manager.subprocess.run", side_effect=run):
            self.assertFalse(waf_manager.reload_waf_rules(["bad"]))
        self.assertEqual(self.read(), "old\n")
        self.assertEqual(len(calls), 2)
        self.assertFalse(os.path.exists(self.path + ".new"))

    def test_a_first_ever_rules_file_that_will_not_load_is_removed(self):
        with patch("src.util.waf_manager.subprocess.run", side_effect=subprocess.CalledProcessError(1, ["nginx"])):
            self.assertFalse(waf_manager.reload_waf_rules(["bad"]))
        self.assertFalse(os.path.exists(self.path))

    def test_a_failed_backup_or_staging_write_never_deletes_the_live_rules(self):
        for name, target in (
            ("backup copy fails", "src.util.waf_manager.shutil.copy2"),
            ("staged write fails", "src.util.waf_manager.open"),
        ):
            with self.subTest(name=name):
                with open(self.path, "w") as f:
                    f.write("old\n")
                real_open = open

                def selective_open(file, mode="r", *a, **kw):
                    if str(file).endswith(".new") and "w" in mode:
                        raise OSError("disk full")
                    return real_open(file, mode, *a, **kw)

                kwargs = {"side_effect": OSError("disk full")} if "copy2" in target else {"new": selective_open, "create": True}
                with patch(target, **kwargs), patch("src.util.waf_manager.subprocess.run") as run:
                    self.assertFalse(waf_manager.reload_waf_rules(["new"]))
                run.assert_not_called()
                self.assertEqual(self.read(), "old\n", "the untouched live rules must survive")
                self.assertFalse(os.path.exists(self.path + ".new"))

    def test_the_live_file_is_never_partially_written(self):
        with open(self.path, "w") as f:
            f.write("old\n")
        with patch("src.util.waf_manager.os.replace", side_effect=OSError("disk full")), patch("src.util.waf_manager.subprocess.run"):
            self.assertFalse(waf_manager.reload_waf_rules(["new"]))
        self.assertEqual(self.read(), "old\n")


if __name__ == "__main__":
    unittest.main()
