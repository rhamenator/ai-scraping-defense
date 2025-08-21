import logging

from src.shared import log_filter  # ensures filter is applied


def test_sensitive_data_filter_masks_data(caplog):
    logger = logging.getLogger("test_logger")
    with caplog.at_level(logging.INFO):
        logger.info("User 192.168.1.1 used api_key=ABC123 and password=secret")
    message = caplog.messages[0]
    assert "192.168.1.1" not in message
    assert "api_key=ABC123" not in message
    assert "password=secret" not in message
    assert "[REDACTED_IP]" in message
    assert "api_key=<redacted>" in message
    assert "password=<redacted>" in message
