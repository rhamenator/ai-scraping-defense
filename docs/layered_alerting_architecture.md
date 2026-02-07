# Layered Alerting and HTTP Utility Structure

This document describes the new layered alerting architecture implemented in the AI Scraping Defense system. The structure provides clean separation of concerns, improved maintainability, and extensible alert delivery mechanisms.

## Architecture Overview

The alerting system is organized in three layers:

1. **HTTP Client Layer (`http_client.py`)** - Provides low-level HTTP communication
2. **Generic Alert Layer (`http_alert.py`)** - Handles generic alert formatting and delivery
3. **Service-Specific Layer (`slack_alert.py`)** - Implements service-specific formatting and protocols

```
┌─────────────────────┐
│  AI Webhook System  │
│   (ai_webhook.py)   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐    ┌─────────────────────┐
│   Slack Alerts      │    │  Generic Webhooks   │
│  (slack_alert.py)   │    │  (http_alert.py)    │
└──────────┬──────────┘    └──────────┬──────────┘
           │                          │
           └─────────┬─────────────────┘
                     ▼
           ┌─────────────────────┐
           │   HTTP Client       │
           │  (http_client.py)   │
           └─────────────────────┘
```

## Components

### 1. AsyncHttpClient (`shared/http_client.py`)

**Purpose**: Async context-managed HTTP client abstraction using httpx.AsyncClient

**Key Features**:
- Async context manager for proper connection lifecycle management
- Configurable timeouts and connection pooling
- Helper methods for common HTTP operations (JSON POST, GET)
- Comprehensive error handling and logging
- Graceful fallback when httpx is not available

**Usage Example**:
```python
async with AsyncHttpClient(timeout=10.0) as client:
    response = await client.async_post_json(
        "https://api.example.com/webhook",
        {"message": "test"},
        headers={"Authorization": "Bearer token"}
    )
```

### 2. HttpAlertSender (`shared/http_alert.py`)

**Purpose**: Generic async alert sender for webhook/API-based alerts

**Key Features**:
- Generic alert payload formatting with extensible structure
- Configurable retry logic and error handling
- Support for multiple HTTP methods and content types
- MultiChannelAlertSender for sending to multiple endpoints
- Base class for service-specific implementations

**Usage Example**:
```python
alert_sender = HttpAlertSender(
    webhook_url="https://hooks.example.com/webhook",
    timeout=10.0,
    max_retry_attempts=3
)

success = await alert_sender.send_alert({
    "message": "Alert from AI Defense System",
    "severity": "high",
    "details": {"ip": "192.168.1.1"}
})
```

### 3. SlackAlertSender (`shared/slack_alert.py`)

**Purpose**: Slack-specific alert formatting and sending logic

**Key Features**:
- Rich Slack message formatting with emoji and markdown
- Structured attachments with color coding
- Automatic emoji selection based on alert type/reason
- Support for channel override and bot customization
- Proper handling of nested alert data structures

**Usage Example**:
```bash
# Set your Slack webhook URL in the environment (example placeholder)
export ALERT_SLACK_WEBHOOK_URL="https://hooks.example.com/services/REDACTED/REDACTED/REDACTED"
```

```python
slack_sender = SlackAlertSender(
    username="AI Defense Bot",
    icon_emoji=":shield:"
)

await slack_sender.send_slack_alert({
    "reason": "High Combined Score (0.95)",
    "event_type": "suspicious_activity_detected",
    "timestamp_utc": "2024-01-01T12:00:00Z",
    "details": {
        "ip": "192.168.1.1",
        "user_agent": "suspicious-bot/1.0",
        "path": "/admin"
    }
})
```

## Integration with AI Webhook System

The existing `ai_webhook.py` has been updated to use the new abstractions while maintaining backward compatibility:

- **New Implementation**: Uses the layered alert classes for improved formatting and error handling
- **Legacy Fallback**: Automatically falls back to the original implementation if new abstractions are unavailable
- **Zero Downtime**: The changes are backwards compatible and don't break existing functionality

### Updated Functions

1. **`send_slack_alert()`**: Now uses `SlackAlertSender` with rich formatting
2. **`send_generic_webhook_alert()`**: Now uses `HttpAlertSender` for consistency
3. **Fallback Functions**: Legacy implementations preserved for compatibility

## Extensibility

The layered architecture makes it easy to add new alert channels:

### Adding a New Alert Service

1. **Extend HttpAlertSender**:
```python
class DiscordAlertSender(HttpAlertSender):
    def format_alert_payload(self, alert_data):
        # Discord-specific formatting
        return {
            "content": f"🛡️ **Alert**: {alert_data['message']}",
            "embeds": [...]
        }
```

2. **Update AI Webhook**:
```python
# In ai_webhook.py
async def send_discord_alert(event_data):
    discord_sender = DiscordAlertSender(DISCORD_WEBHOOK_URL)
    await discord_sender.send_alert({...})
```

### Multi-Channel Alerts

```python
multi_sender = MultiChannelAlertSender()
multi_sender.add_channel("slack", SlackAlertSender(slack_url))
multi_sender.add_channel("discord", DiscordAlertSender(discord_url))
multi_sender.add_channel("teams", TeamsAlertSender(teams_url))

# Send to all channels
success_count = await multi_sender.send_alert_to_all(alert_data)
```

## Configuration and Deployment

### Environment Variables

The system continues to use existing environment variables:
- `ALERT_SLACK_WEBHOOK_URL` - Slack webhook URL
- `ALERT_SLACK_WEBHOOK_URL_FILE` - Path to a secret file containing the Slack webhook URL
- `ALERT_GENERIC_WEBHOOK_URL` - Generic webhook URL
- `ALERT_GENERIC_WEBHOOK_URL_FILE` - Path to a secret file containing the generic webhook URL
- `ALERT_METHOD` - Alert method selection (`slack`, `webhook`, `smtp`, `none`)

### Dependencies

- **httpx**: Required for HTTP functionality (graceful fallback available)
- **asyncio**: For async operations
- **logging**: For comprehensive logging

### Error Handling

The new system provides improved error handling:
- **Connection errors**: Automatic retries with exponential backoff
- **Timeout handling**: Configurable timeouts per request
- **Payload errors**: Comprehensive validation and error reporting
- **Fallback mechanisms**: Automatic fallback to legacy implementations

## Testing

The implementation includes comprehensive test coverage:

```bash
# Run the test suite (when dependencies are available)
cd src/
python -c "
import asyncio
from shared.slack_alert import SlackAlertSender

async def test():
    sender = SlackAlertSender()
    result = await sender.send_test_slack_alert()
    print(f'Test result: {result}')

asyncio.run(test())
"
```

## Migration Guide

### For Existing Deployments

1. **No Immediate Changes Required**: The system automatically uses new abstractions when available
2. **Gradual Migration**: Can be deployed without downtime
3. **Configuration**: Uses existing environment variables

### For Developers

1. **New Alert Services**: Use the new base classes for consistency
2. **Custom Formatting**: Override `format_alert_payload()` methods
3. **Error Handling**: Leverage built-in retry and fallback mechanisms

## Benefits

1. **Maintainability**: Clear separation of concerns and modular design
2. **Extensibility**: Easy to add new alert services and channels
3. **Reliability**: Improved error handling and fallback mechanisms
4. **Testing**: Comprehensive test coverage and mock support
5. **Performance**: Connection pooling and async operations
6. **Compatibility**: Backward compatible with existing deployments

## Future Enhancements

1. **Alert Templating**: Configurable message templates
2. **Rate Limiting**: Built-in rate limiting for alert delivery
3. **Alert Aggregation**: Batching and deduplication
4. **Monitoring**: Metrics and health checks for alert delivery
5. **Additional Services**: Teams, Discord, Email, SMS integrations
