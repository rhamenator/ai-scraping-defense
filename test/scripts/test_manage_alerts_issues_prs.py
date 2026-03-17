import json

from scripts.manage_alerts_issues_prs import AlertManager
from scripts.security_response_plan import build_response_plan_entry


def test_manager_writes_response_plan(tmp_path):
    manager = AlertManager.__new__(AlertManager)
    manager.owner = "rhamenator"
    manager.repo = "ai-scraping-defense"
    manager.dry_run = True
    manager.plan_output = str(tmp_path / "security-response-plan.json")
    manager.response_plan_entries = [
        build_response_plan_entry(
            source="dependabot",
            dedupe_key="dependabot:test",
            title="[Dependabot] critical: example",
            severity="critical",
            occurrences=1,
        )
    ]
    manager.log_action = lambda *_args, **_kwargs: None

    manager.write_response_plan()

    payload = json.loads((tmp_path / "security-response-plan.json").read_text())
    assert payload["summary"]["issues"] == 1
    assert payload["summary"]["operator_pages"] == 1
    assert payload["entries"][0]["automated_response"] == "expedite_patch"


def test_normalize_alert_key_handles_secret_and_dependabot():
    manager = AlertManager.__new__(AlertManager)

    secret_key = manager.normalize_alert_key(
        {
            "secret_type": "slack_webhook_url",
            "secret_type_display_name": "Slack",
        }
    )
    dependabot_key = manager.normalize_alert_key(
        {
            "security_advisory": {"ghsa_id": "GHSA-aaaa-bbbb-cccc"},
            "dependency": {"package": "requests"},
            "security_vulnerability": {"severity": "high"},
        }
    )

    assert secret_key == ":".join(["secret-scanning", "slack_webhook_url"])
    assert dependabot_key == ":".join(["dependabot", "GHSA-aaaa-bbbb-cccc"])
