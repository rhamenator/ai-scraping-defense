import json

from scripts.security_response_plan import (
    build_plan_payload,
    build_response_plan_entry,
    summarize_response_plan,
    write_plan_payload,
)


def test_secret_scanning_pages_and_rotates_credentials(tmp_path):
    entry = build_response_plan_entry(
        source="secret_scanning",
        dedupe_key="secret-scanning:slack_webhook_url",
        title="[Secret] Slack Webhook URL exposure",
        severity="low",
        occurrences=2,
    )

    assert entry.severity == "critical"
    assert entry.create_issue is True
    assert entry.page_operator is True
    assert entry.automated_response == "rotate_credentials"


def test_critical_code_scanning_pages_and_hotfixes():
    entry = build_response_plan_entry(
        source="code_scanning",
        dedupe_key="code-scanning:CodeQL:py/sql-injection:critical",
        title="[Security] CodeQL: py/sql-injection",
        severity="critical",
        occurrences=1,
    )

    assert entry.create_issue is True
    assert entry.page_operator is True
    assert entry.automated_response == "expedite_hotfix"


def test_low_code_scanning_stays_backlog_only():
    entry = build_response_plan_entry(
        source="code_scanning",
        dedupe_key="code-scanning:CodeQL:py/style:low",
        title="[Security] CodeQL: py/style",
        severity="low",
        occurrences=1,
    )

    assert entry.create_issue is False
    assert entry.page_operator is False
    assert entry.automated_response is None


def test_plan_payload_writes_summary(tmp_path):
    entries = [
        build_response_plan_entry(
            source="secret_scanning",
            dedupe_key="secret-scanning:a",
            title="secret",
            severity="critical",
            occurrences=1,
        ),
        build_response_plan_entry(
            source="dependabot",
            dedupe_key="dependabot:b",
            title="dep",
            severity="medium",
            occurrences=1,
        ),
    ]

    payload = build_plan_payload(
        repository="rhamenator/ai-scraping-defense",
        mode="DRY RUN",
        entries=entries,
    )
    output_path = tmp_path / "plan.json"
    write_plan_payload(output_path, payload)

    persisted = json.loads(output_path.read_text())
    summary = summarize_response_plan(entries)

    assert persisted["repository"] == "rhamenator/ai-scraping-defense"
    assert persisted["mode"] == "DRY RUN"
    assert persisted["summary"] == summary
    assert len(persisted["entries"]) == 2
