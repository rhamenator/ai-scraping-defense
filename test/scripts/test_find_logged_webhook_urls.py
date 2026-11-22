"""The webhook-log scanner reports where URLs were logged and never prints them (#1906)."""

import contextlib
import io
import secrets
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import find_logged_webhook_urls as scanner  # noqa: E402


def run(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        status = scanner.main(list(args))
    return status, out.getvalue(), err.getvalue()


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)
        self.token = secrets.token_hex(12)

    def write(self, name: str, text: str) -> Path:
        path = self.tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_known_webhook_shapes_are_found_by_file_and_line_and_never_printed(self):
        self.write(
            "app.log",
            f"ok line\nError for url 'https://hooks.slack.com/services/T000/B000/{self.token}'\n"
            f"https://discord.com/api/webhooks/123456789/{self.token} failed\n"
            f"https://example.webhook.office.com/webhookb2/{self.token}@x/IncomingWebhook/abc/def\n",
        )

        status, out, err = run(str(self.tmp))

        self.assertEqual(status, 1)
        self.assertEqual(len(out.strip().splitlines()), 3)
        self.assertIn("app.log:2: slack", out)
        self.assertIn("app.log:3: discord", out)
        self.assertIn("app.log:4: teams", out)
        self.assertNotIn(self.token, out + err)
        self.assertNotIn("hooks.slack.com", out + err)
        self.assertIn("Scanned 1 file(s); 3 webhook URL occurrence(s) found.", err)

    def test_the_same_url_gets_the_same_id_and_different_urls_differ(self):
        url_a = f"https://hooks.slack.com/services/T0/B0/{self.token}"
        url_b = f"https://hooks.slack.com/services/T0/B0/{secrets.token_hex(12)}"
        self.write("a.log", f"{url_a}\n{url_a}\n{url_b}\n")
        _, out, _ = run(str(self.tmp / "a.log"))
        ids = [line.rsplit("id=", 1)[1].rstrip(")") for line in out.strip().splitlines()]
        self.assertEqual(ids[0], ids[1])
        self.assertNotEqual(ids[0], ids[2])

    def test_a_configured_url_is_found_even_if_it_has_no_known_shape(self):
        custom = f"https://alerts.example.test/hooks/{self.token}"
        env_file = self.write(".env", f"ALERT_GENERIC_WEBHOOK_URL={custom}\nOTHER=value\n")
        self.write("old.log", f"posting to {custom} failed\nnothing here\n")

        status, out, err = run("--env-file", str(env_file), str(self.tmp / "old.log"))

        self.assertEqual(status, 1)
        self.assertIn("old.log:1: configured", out)
        self.assertNotIn(self.token, out + err)

    def test_every_webhook_url_variable_is_recognised_including_escalation_and_file_variants(self):
        urls = {name: f"https://alerts.example.test/{name.lower()}/{secrets.token_hex(8)}" for name in (
            "ESCALATION_WEBHOOK_URL", "ALERT_SLACK_WEBHOOK_URL", "ALERT_GENERIC_WEBHOOK_URL", "WEBHOOK_URL")}
        secret_file = self.write("secret.txt", "https://alerts.example.test/from-a-file/" + self.token + "\n")
        env = "\n".join(f"{name}={url}" for name, url in urls.items()) + f"\nALERT_TEAMS_WEBHOOK_URL_FILE={secret_file}\nNOT_A_WEBHOOK=https://x.test/y\n"
        env_file = self.write(".env", env)
        self.write("app.log", "\n".join(f"failed {url}" for url in [*urls.values(), "https://alerts.example.test/from-a-file/" + self.token]) + "\nNOT_A_WEBHOOK https://x.test/y\n")

        status, out, err = run("--env-file", str(env_file), str(self.tmp / "app.log"))

        self.assertEqual(status, 1)
        self.assertEqual(len(out.strip().splitlines()), 5)
        self.assertIn("5 configured URL(s) from 5 recognised variable(s)", err)
        self.assertNotIn(self.token, out + err)
        for url in urls.values():
            self.assertNotIn(url.rsplit("/", 1)[1], out + err)

    def test_the_summary_says_what_was_checked_so_a_clean_result_is_not_over_read(self):
        self.write("clean.log", "nothing\n")
        _, _, err = run(str(self.tmp / "clean.log"))
        self.assertIn("Checked for: Slack, Teams and Discord URL shapes, and 0 configured URL(s) from 0 recognised", err)
        self.assertIn("A webhook of another kind", err)

    def test_clean_files_and_plain_origins_are_not_reported(self):
        self.write("clean.log", "connecting to https://hooks.slack.com\nhttps://example.com/path\nplain text\n")

        status, out, err = run(str(self.tmp))

        self.assertEqual(status, 0)
        self.assertEqual(out, "")
        self.assertIn("0 webhook URL occurrence(s)", err)

    def test_binary_or_missing_files_do_not_crash_the_scan(self):
        (self.tmp / "blob.bin").write_bytes(bytes(range(256)) * 10)
        status, _, err = run(str(self.tmp), str(self.tmp / "does-not-exist"))
        self.assertEqual(status, 0)
        self.assertIn("Scanned 1 file(s)", err)


if __name__ == "__main__":
    unittest.main()
