import io
import logging

from src.shared import log_filter


def test_sensitive_data_formatter_masks_data():
    logger = logging.getLogger("test_logger")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_filter.configure_sensitive_logging(logger)
    logger.info("User 192.168.0.1 used api_key=ABC123 and password=secret")
    message = stream.getvalue().strip()
    assert "192.168.0.1" not in message
    assert "api_key=ABC123" not in message
    assert "password=secret" not in message
    assert "[REDACTED_IP]" in message
    assert "api_key=<redacted>" in message
    assert "password=<redacted>" in message


def test_invalid_ip_not_redacted():
    logger = logging.getLogger("invalid_ip")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_filter.configure_sensitive_logging(logger)
    logger.info("Bad IP 999.999.999.999 detected")
    message = stream.getvalue().strip()
    assert "999.999.999.999" in message
    assert "[REDACTED_IP]" not in message


def test_multiple_handlers_each_get_masked():
    logger = logging.getLogger("multi")
    stream1, stream2 = io.StringIO(), io.StringIO()
    handler1 = logging.StreamHandler(stream1)
    handler1.setFormatter(logging.Formatter("%(message)s"))
    handler2 = logging.StreamHandler(stream2)
    handler2.setFormatter(logging.Formatter("{message}", style="{"))
    logger.addHandler(handler1)
    logger.addHandler(handler2)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_filter.configure_sensitive_logging(logger)
    logger.info("User 192.168.0.1 password=secret")

    out1, out2 = stream1.getvalue(), stream2.getvalue()
    assert "[REDACTED_IP]" in out1 and "[REDACTED_IP]" in out2
    assert "password=<redacted>" in out1 and "password=<redacted>" in out2


def test_formatter_preserves_msg_and_args():
    logger = logging.getLogger("args")
    stream = io.StringIO()
    records = []

    class RecordingHandler(logging.StreamHandler):
        def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - simple
            records.append(record)
            super().emit(record)

    handler = RecordingHandler(stream)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_filter.configure_sensitive_logging(logger)
    logger.info("User %s from %s api_key=%s", "alice", "192.168.0.1", "ABC123")
    record = records[0]
    message = stream.getvalue().strip()
    assert record.msg == "User %s from %s api_key=%s"
    assert record.args == ("alice", "192.168.0.1", "ABC123")
    assert "[REDACTED_IP]" in message
    assert "api_key=<redacted>" in message


def test_configure_sensitive_logging_idempotent_and_no_monkey_patch():
    orig_get_logger = logging.getLogger
    logger = logging.getLogger("idempotent")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_filter.configure_sensitive_logging(logger)
    first_formatter = handler.formatter
    log_filter.configure_sensitive_logging(logger)
    second_formatter = handler.formatter
    logger.info("password=secret")

    assert first_formatter is second_formatter
    assert isinstance(first_formatter, log_filter.SensitiveDataFormatter)
    assert logging.getLogger is orig_get_logger
    assert "password=<redacted>" in stream.getvalue()
