"""Tests for GDPR compliance module."""

import datetime
import json
from unittest.mock import MagicMock, patch

import pytest

from src.shared.gdpr import (
    ConsentRecord,
    ConsentType,
    DataCategory,
    DataDeletionRequest,
    GDPRComplianceManager,
    get_gdpr_manager,
)


@pytest.fixture
def mock_redis():
    """Mock Redis connection."""
    redis_mock = MagicMock()
    redis_mock.get.return_value = None
    redis_mock.set.return_value = True
    redis_mock.expire.return_value = True
    redis_mock.delete.return_value = True
    redis_mock.scan_iter.return_value = iter([])
    redis_mock.lpush.return_value = True
    redis_mock.ltrim.return_value = True
    redis_mock.lrange.return_value = []
    return redis_mock


@pytest.fixture
def gdpr_manager(mock_redis):
    """Create GDPR manager with mocked Redis."""
    with patch("src.shared.gdpr.get_redis_connection", return_value=mock_redis):
        manager = GDPRComplianceManager()
        return manager


def test_consent_record_creation():
    """Test creating a consent record."""
    consent = ConsentRecord(
        user_id="user123",
        consent_type=ConsentType.ANALYTICS,
        granted=True,
        ip_address="192.168.1.1",
    )
    
    assert consent.user_id == "user123"
    assert consent.consent_type == ConsentType.ANALYTICS
    assert consent.granted is True
    assert consent.ip_address == "192.168.1.1"
    
    # Check to_dict
    consent_dict = consent.to_dict()
    assert consent_dict["user_id"] == "user123"
    assert consent_dict["consent_type"] == ConsentType.ANALYTICS


def test_data_deletion_request_creation():
    """Test creating a data deletion request."""
    request = DataDeletionRequest(
        request_id="req123",
        user_id="user456",
        email="user@example.com",
        data_categories=[DataCategory.IP_ADDRESS, DataCategory.ACCESS_LOGS],
    )
    
    assert request.request_id == "req123"
    assert request.user_id == "user456"
    assert request.email == "user@example.com"
    assert request.status == "pending"
    assert DataCategory.IP_ADDRESS in request.data_categories


def test_record_consent(gdpr_manager, mock_redis):
    """Test recording user consent."""
    consent = gdpr_manager.record_consent(
        user_id="user123",
        consent_type=ConsentType.ANALYTICS,
        granted=True,
        ip_address="192.168.1.1",
    )
    
    assert consent.user_id == "user123"
    assert consent.granted is True
    mock_redis.set.assert_called_once()


def test_check_consent_granted(gdpr_manager, mock_redis):
    """Test checking consent when it is granted."""
    consent_data = {
        "user_id": "user123",
        "consent_type": ConsentType.ANALYTICS.value,
        "granted": True,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    mock_redis.get.return_value = json.dumps(consent_data)
    
    has_consent = gdpr_manager.check_consent("user123", ConsentType.ANALYTICS)
    assert has_consent is True


def test_check_consent_not_granted(gdpr_manager, mock_redis):
    """Test checking consent when it is not granted."""
    consent_data = {
        "user_id": "user123",
        "consent_type": ConsentType.ANALYTICS.value,
        "granted": False,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    mock_redis.get.return_value = json.dumps(consent_data)
    
    has_consent = gdpr_manager.check_consent("user123", ConsentType.ANALYTICS)
    assert has_consent is False


def test_check_consent_expired(gdpr_manager, mock_redis):
    """Test checking consent when it has expired."""
    expired_time = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    ).isoformat().replace("+00:00", "Z")
    
    consent_data = {
        "user_id": "user123",
        "consent_type": ConsentType.ANALYTICS.value,
        "granted": True,
        "expires_at": expired_time,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    mock_redis.get.return_value = json.dumps(consent_data)
    
    has_consent = gdpr_manager.check_consent("user123", ConsentType.ANALYTICS)
    assert has_consent is False


def test_essential_consent_always_granted(gdpr_manager):
    """Test that essential consent is always granted."""
    has_consent = gdpr_manager.check_consent("user123", ConsentType.ESSENTIAL)
    assert has_consent is True


def test_request_data_deletion(gdpr_manager, mock_redis):
    """Test requesting data deletion."""
    deletion_request = gdpr_manager.request_data_deletion(
        user_id="user123",
        email="user@example.com",
        data_categories=[DataCategory.IP_ADDRESS],
    )
    
    assert deletion_request.user_id == "user123"
    assert deletion_request.email == "user@example.com"
    assert deletion_request.status == "pending"
    mock_redis.set.assert_called()
    mock_redis.lpush.assert_called()


def test_minimize_data(gdpr_manager):
    """Test data minimization."""
    data = {
        "timestamp": "2025-11-21T00:00:00Z",
        "event_type": "request",
        "ip_address": "192.168.1.100",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Very long user agent string that should be truncated to preserve privacy",
        "path": "/api/test",
        "method": "GET",
        "status_code": 200,
        "extra_field": "should be removed",
    }
    
    minimized = gdpr_manager.minimize_data(data)
    
    # Check IP is anonymized
    assert minimized["ip_address"] == "192.168.1.0"
    
    # Check user agent is truncated
    assert len(minimized["user_agent"]) <= 100
    
    # Check extra field is removed
    assert "extra_field" not in minimized
    
    # Check essential fields are kept
    assert minimized["timestamp"] == data["timestamp"]
    assert minimized["path"] == data["path"]


def test_minimize_data_ipv6(gdpr_manager):
    """Test data minimization with IPv6 address."""
    data = {
        "ip_address": "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
        "timestamp": "2025-11-21T00:00:00Z",
    }
    
    minimized = gdpr_manager.minimize_data(data)
    
    # IPv6 should be truncated
    assert minimized["ip_address"].endswith("::0")
    assert len(minimized["ip_address"]) <= 26


def test_generate_compliance_report(gdpr_manager, mock_redis):
    """Test generating compliance report."""
    mock_redis.scan_iter.side_effect = [
        iter(["consent:1", "consent:2"]),  # consent records
        iter(["deletion:1"]),  # deletion requests
    ]
    mock_redis.lrange.return_value = [b'{"event": "test"}']
    
    report = gdpr_manager.generate_compliance_report()
    
    assert "timestamp" in report
    assert report["gdpr_enabled"] is True
    assert "dpo_contact" in report
    assert "statistics" in report
    assert report["statistics"]["total_consent_records"] == 2
    assert report["statistics"]["total_deletion_requests"] == 1


def test_get_gdpr_manager():
    """Test getting global GDPR manager instance."""
    manager1 = get_gdpr_manager()
    manager2 = get_gdpr_manager()
    
    # Should return same instance
    assert manager1 is manager2


@patch("src.shared.gdpr.GDPR_ENABLED", False)
def test_minimize_data_when_disabled():
    """Test that data minimization is skipped when GDPR is disabled."""
    manager = GDPRComplianceManager()
    
    data = {
        "ip_address": "192.168.1.100",
        "user_agent": "Long user agent",
        "extra_field": "should be kept",
    }
    
    result = manager.minimize_data(data)
    
    # When GDPR is disabled, data should be returned as-is
    assert result == data


def test_process_deletion_request(gdpr_manager, mock_redis):
    """Test processing a deletion request."""
    request_data = {
        "request_id": "req123",
        "user_id": "user123",
        "email": "user@example.com",
        "data_categories": ["ip_address", "access_logs"],
        "status": "pending",
    }
    mock_redis.get.return_value = json.dumps(request_data)
    mock_redis.scan_iter.return_value = iter(["key1", "key2"])
    
    result = gdpr_manager.process_deletion_request("req123")
    
    assert result is True
    # Should have called delete for user data
    assert mock_redis.delete.called


def test_process_deletion_request_not_found(gdpr_manager, mock_redis):
    """Test processing a non-existent deletion request."""
    mock_redis.get.return_value = None
    
    result = gdpr_manager.process_deletion_request("nonexistent")
    
    assert result is False


@pytest.mark.asyncio
async def test_cleanup_expired_data(gdpr_manager):
    """Test cleaning up expired data."""
    deleted_count = await gdpr_manager.cleanup_expired_data()
    
    # Should return a count (even if 0)
    assert isinstance(deleted_count, int)
    assert deleted_count >= 0
