from unittest.mock import patch

from src.shared import operational_events


def test_publish_operational_event_persists_security_event():
    with (
        patch.object(operational_events, "record_security_event") as mock_record,
        patch.object(operational_events, "_events_enabled", return_value=False),
    ):
        result = operational_events.publish_operational_event(
            "blocklist_sync_completed",
            {"source": "community", "ip": "1.2.3.4", "added": 2},
        )

    assert result is None
    mock_record.assert_called_once()
    assert mock_record.call_args.kwargs["action"] == "blocklist_sync_completed"
