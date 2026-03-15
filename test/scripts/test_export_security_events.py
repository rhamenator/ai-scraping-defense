import json

from scripts import export_security_events


def test_main_writes_jsonl_to_stdout(monkeypatch, capsys):
    monkeypatch.setattr(
        export_security_events,
        "export_security_events",
        lambda **_kwargs: (
            1,
            json.dumps({"event_type": "audit_event", "payload": {}}) + "\n",
        ),
    )

    rc = export_security_events.main([])
    captured = capsys.readouterr()

    assert rc == 0
    assert '"event_type": "audit_event"' in captured.out


def test_main_reports_output_path(monkeypatch, capsys):
    monkeypatch.setattr(
        export_security_events,
        "export_security_events",
        lambda **_kwargs: (3, ""),
    )

    rc = export_security_events.main(["--output", "reports/security-events.jsonl"])
    captured = capsys.readouterr()

    assert rc == 0
    assert "Exported 3 security events" in captured.out
