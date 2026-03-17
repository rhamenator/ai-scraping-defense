import importlib
import json
import os
import unittest

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


def test_main_output_file_permissions(tmp_path):
    output = tmp_path / "events.jsonl"
    db_path = tmp_path / "security_events.db"

    with unittest.mock.patch.dict(
        os.environ, {"SECURITY_EVENTS_DB_PATH": str(db_path)}, clear=False
    ):
        from src.shared import security_events

        module = importlib.reload(security_events)
        importlib.reload(export_security_events)
        module.record_security_event("audit_event", payload={"api_key": "sek"})
        rc = export_security_events.main(["--output", str(output)])

    assert rc == 0
    assert output.exists()
    if os.name != "nt":
        assert output.stat().st_mode & 0o777 == 0o600
