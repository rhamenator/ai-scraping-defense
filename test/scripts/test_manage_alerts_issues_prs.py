import json
import runpy
import sys
from pathlib import Path

import pytest

from scripts.manage_alerts_issues_prs import AlertManager
from scripts.security_response_plan import build_response_plan_entry


def test_manager_runs_as_script_from_repository_root(monkeypatch, capsys):
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts/manage_alerts_issues_prs.py"
    monkeypatch.syspath_prepend(str(script.parent))
    monkeypatch.setattr(sys, "argv", [str(script), "--help"])
    with pytest.raises(SystemExit) as exit_status:
        runpy.run_path(str(script), run_name="__main__")
    assert exit_status.value.code == 0
    assert "--owner" in capsys.readouterr().out


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
