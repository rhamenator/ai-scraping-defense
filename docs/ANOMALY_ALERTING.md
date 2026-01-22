# Anomaly Alerting Actions

Anomaly scores above the publish threshold are emitted on the `anomaly_events`
Redis channel. The alert subscriber (`src/ai_service/alerts.py`) can now trigger
actions based on the score and configuration.

## Configuration

Environment variables:

- `ANOMALY_ALERT_ACTIONS` (default: `alert`)
  - Comma-separated actions: `alert`, `blocklist`, `escalate`, `notify`
- `ANOMALY_ALERT_THRESHOLD` (default: `0.9`)
- `ANOMALY_BLOCK_THRESHOLD` (default: `0.97`)
- `ANOMALY_ESCALATE_THRESHOLD` (default: `0.95`)

## Actions

- `alert` / `notify`: Sends alerts via the configured alert channel.
- `blocklist`: Adds the IP to the blocklist when the score meets
  `ANOMALY_BLOCK_THRESHOLD`.
- `escalate`: Publishes an operational event requesting escalation.

## Notes

- `ANOMALY_SCORE_THRESHOLD` (in `src/shared/anomaly_detector.py`) controls when
  anomaly events are published to Redis.
- If an IP is missing from the anomaly features, blocklist actions are skipped.
