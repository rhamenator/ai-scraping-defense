import logging

from src.shared import log_filter  # ensures filter is applied


def test_sensitive_data_filter_masks_data(caplog):
    logger = logging.getLogger("test_logger")
    with caplog.at_level(logging.INFO):
        logger.info("User 192.168.0.1 used api_key=ABC123 and password=secret")
    message = caplog.messages[0]
    assert "192.168.0.1" not in message
    assert "api_key=ABC123" not in message
    assert "password=secret" not in message
    assert "[REDACTED_IP]" in message
    assert "api_key=<redacted>" in message
    assert "password=<redacted>" in message


def test_invalid_ip_not_redacted(caplog):
    logger = logging.getLogger("invalid_ip")
    with caplog.at_level(logging.INFO):
        logger.info("Bad IP 999.999.999.999 detected")
    message = caplog.messages[0]
    assert "999.999.999.999" in message
    assert "[REDACTED_IP]" not in message


def test_apply_sensitive_data_filter_idempotent():
    first_get_logger = logging.getLogger
    log_filter.apply_sensitive_data_filter()
    second_get_logger = logging.getLogger
    log_filter.apply_sensitive_data_filter()
    third_get_logger = logging.getLogger

    root_logger = logging.getLogger()
    assert root_logger.filters.count(log_filter._FILTER) == 1

    logger = logging.getLogger("idempotent")
    assert logger.filters.count(log_filter._FILTER) == 1

    assert first_get_logger is second_get_logger is third_get_logger
