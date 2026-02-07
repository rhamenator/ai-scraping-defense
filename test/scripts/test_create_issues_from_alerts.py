import unittest

from scripts.create_issues_from_alerts import IssueCreator


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


if __name__ == "__main__":
    unittest.main()
