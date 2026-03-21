import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import create_issues_from_alerts
from scripts.create_issues_from_alerts import IssueCreator
from scripts.security_response_plan import build_response_plan_entry


class TestCreateIssuesFromAlerts(unittest.TestCase):
    def _creator(self) -> IssueCreator:
        # Avoid network initialization in IssueCreator.__init__.
        return IssueCreator.__new__(IssueCreator)

    def test_code_scanning_title_includes_rule_id(self):
        creator = self._creator()
        alerts_a = [
            {
                "tool": {"name": "CodeQL"},
                "rule": {
                    "id": "py/sql-injection",
                    "name": "SQL Injection",
                    "severity": "high",
                },
            }
        ]
        alerts_b = [
            {
                "tool": {"name": "CodeQL"},
                "rule": {
                    "id": "py/other-injection",
                    "name": "SQL Injection",
                    "severity": "high",
                },
            }
        ]
        title_a = creator.create_issue_title_for_code_scanning("x", alerts_a)
        title_b = creator.create_issue_title_for_code_scanning("y", alerts_b)

        self.assertIn("py/sql-injection", title_a)
        self.assertIn("py/other-injection", title_b)
        self.assertNotEqual(title_a, title_b)

    def test_code_scanning_body_includes_dedupe_marker(self):
        creator = self._creator()
        alerts = [
            {
                "tool": {"name": "CodeQL"},
                "rule": {
                    "id": "py/sql-injection",
                    "name": "SQL Injection",
                    "severity": "high",
                    "security_severity_level": "high",
                },
                "number": 1,
                "html_url": "https://example.invalid/alert/1",
                "most_recent_instance": {
                    "location": {"path": "src/app.py", "start_line": 10, "end_line": 10}
                },
            }
        ]
        body = creator.create_issue_body_for_code_scanning(alerts)
        self.assertIn(
            "alert-group-key: code-scanning:CodeQL:py/sql-injection:high", body
        )

    def test_secret_scanning_body_includes_dedupe_marker(self):
        creator = self._creator()
        alerts = [
            {
                "secret_type": "slack_webhook_url",
                "secret_type_display_name": "Slack Webhook URL",
                "number": 1,
                "html_url": "https://example.invalid/secret/1",
                "locations": [
                    {"details": {"path": "README.md", "start_line": 1}},
                ],
            }
        ]
        body = creator.create_issue_body_for_secret_scanning(alerts)
        self.assertIn(
            "alert-group-key: secret-scanning:slack_webhook_url",
            body,
        )

    def test_dependabot_body_includes_dedupe_marker(self):
        creator = self._creator()
        alerts = [
            {
                "vulnerableManifestFilename": "requirements.lock",
                "securityAdvisory": {
                    "ghsaId": "GHSA-aaaa-bbbb-cccc",
                    "summary": "Example advisory",
                    "severity": "HIGH",
                    "permalink": "https://example.invalid/advisory",
                },
                "securityVulnerability": {
                    "severity": "HIGH",
                    "vulnerableVersionRange": "< 1.2.3",
                    "firstPatchedVersion": {"identifier": "1.2.3"},
                    "package": {"name": "examplepkg", "ecosystem": "PIP"},
                },
            }
        ]
        body = creator.create_issue_body_for_dependabot(alerts)
        self.assertIn("alert-group-key: dependabot:GHSA-aaaa-bbbb-cccc", body)

    def test_write_response_plan_output(self):
        creator = self._creator()
        creator.owner = "rhamenator"
        creator.repo = "ai-scraping-defense"
        creator.dry_run = True
        creator.response_plan_entries = [
            build_response_plan_entry(
                source="secret_scanning",
                dedupe_key="secret-scanning:test",
                title="[Secret] test",
                severity="critical",
                occurrences=1,
            )
        ]
        creator.log = lambda *_args, **_kwargs: None

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "response-plan.json"
            creator.plan_output = str(output_path)
            creator.write_response_plan()
            with output_path.open("r", encoding="utf-8") as handle:
                payload = handle.read()

        self.assertIn('"repository": "rhamenator/ai-scraping-defense"', payload)
        self.assertIn('"operator_pages": 1', payload)

    def test_sanitize_message_redacts_tokens(self):
        message = (
            "failure with gho_123456789012345678901234567890123456 and "
            "github_pat_abcdefghijklmnopqrstuvwxyz1234567890 and Bearer secret-token"
        )

        sanitized = create_issues_from_alerts._sanitize_message_standalone(message)

        self.assertNotIn("gho_123456789012345678901234567890123456", sanitized)
        self.assertNotIn("github_pat_abcdefghijklmnopqrstuvwxyz1234567890", sanitized)
        self.assertIn("[REDACTED_TOKEN]", sanitized)
        self.assertIn("Bearer [REDACTED]", sanitized)

    def test_main_sanitizes_fatal_output(self):
        argv = [
            "create_issues_from_alerts.py",
            "--owner",
            "rhamenator",
            "--repo",
            "ai-scraping-defense",
            "--token",
            "gho_123456789012345678901234567890123456",
        ]
        fatal_error = RuntimeError(
            "Bearer secret-token gho_123456789012345678901234567890123456"
        )

        with mock.patch("sys.argv", argv), mock.patch.object(
            create_issues_from_alerts, "IssueCreator", side_effect=fatal_error
        ), mock.patch("builtins.print") as mock_print:
            with self.assertRaises(SystemExit):
                create_issues_from_alerts.main()

        printed = "\n".join(
            " ".join(str(arg) for arg in call.args)
            for call in mock_print.call_args_list
        )
        self.assertNotIn("secret-token", printed)
        self.assertNotIn("gho_123456789012345678901234567890123456", printed)
        self.assertIn("[REDACTED_TOKEN]", printed)


if __name__ == "__main__":
    unittest.main()
