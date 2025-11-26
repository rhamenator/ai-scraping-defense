"""Tests for security data lake module."""

import importlib
import json
import os
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src.security import data_lake
from src.security.data_lake import (
    ThreatCategory,
    ThreatEvent,
    ThreatIntelligence,
    ThreatSeverity,
    apply_data_retention_policy,
    calculate_analytics_metric,
    get_analytics_metrics,
    get_governance_log,
    get_threat_statistics,
    hunt_threats,
    query_threat_intelligence,
    record_threat_event,
)


class TestSecurityDataLake(unittest.TestCase):
    """Test cases for security data lake functionality."""

    def setUp(self):
        """Set up test database before each test."""
        self.test_dir = os.path.dirname(__file__)
        self.temp_db = os.path.join(self.test_dir, "temp_data_lake.db")
        # Clean up old test database
        if os.path.exists(self.temp_db):
            os.remove(self.temp_db)

    def tearDown(self):
        """Clean up test database after each test."""
        if os.path.exists(self.temp_db):
            os.remove(self.temp_db)

    def reload_module_with_temp_db(self):
        """Reload the data_lake module with a test database path."""
        with patch.dict(os.environ, {"SECURITY_DATA_LAKE_PATH": self.temp_db}):
            return importlib.reload(data_lake)

    def test_record_threat_event(self):
        """Test recording a threat event to the data lake."""
        dl_module = self.reload_module_with_temp_db()

        event = dl_module.ThreatEvent(
            timestamp="2024-01-01T00:00:00Z",
            tenant_id="test_tenant",
            category=dl_module.ThreatCategory.BOT_DETECTION,
            severity=dl_module.ThreatSeverity.HIGH,
            source_ip="192.168.1.100",
            source="escalation_engine",
            description="Suspicious bot activity detected",
            details={"user_agent": "BotUA", "score": 0.95},
            threat_score=0.95,
            action_taken="blocked",
        )

        dl_module.record_threat_event(event)

        # Verify the database file was created
        self.assertTrue(os.path.exists(self.temp_db))

        # Verify the event was recorded
        conn = sqlite3.connect(self.temp_db)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(
                "SELECT * FROM threat_events WHERE source_ip = ?", ("192.168.1.100",)
            )
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["category"], "bot_detection")
            self.assertEqual(row["severity"], "high")
            self.assertEqual(row["threat_score"], 0.95)
            self.assertEqual(row["action_taken"], "blocked")

            # Verify details are stored as JSON
            details = json.loads(row["details"])
            self.assertEqual(details["user_agent"], "BotUA")
        finally:
            conn.close()

    def test_threat_intelligence_aggregation(self):
        """Test that threat intelligence is aggregated correctly."""
        dl_module = self.reload_module_with_temp_db()

        # Record multiple events from the same IP
        for i in range(3):
            event = dl_module.ThreatEvent(
                timestamp=f"2024-01-01T00:0{i}:00Z",
                tenant_id="test_tenant",
                category=dl_module.ThreatCategory.BOT_DETECTION,
                severity=dl_module.ThreatSeverity.MEDIUM,
                source_ip="192.168.1.200",
                source="test_source",
                description=f"Event {i}",
                details={"event_num": i},
                threat_score=0.5 + (i * 0.1),
                action_taken="logged",
            )
            dl_module.record_threat_event(event)

        # Check aggregated intelligence
        conn = sqlite3.connect(self.temp_db)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(
                "SELECT * FROM threat_intelligence WHERE identifier = ?",
                ("192.168.1.200",),
            )
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["event_count"], 3)
            self.assertEqual(row["identifier_type"], "ip")
            # Threat score should be weighted average
            expected_score = (0.5 + 0.6 + 0.7) / 3
            self.assertAlmostEqual(row["threat_score"], expected_score, places=2)
        finally:
            conn.close()

    def test_query_threat_intelligence(self):
        """Test querying threat intelligence data."""
        dl_module = self.reload_module_with_temp_db()

        # Create events with different threat scores
        ips = [("10.0.0.1", 0.3), ("10.0.0.2", 0.7), ("10.0.0.3", 0.9)]
        for ip, score in ips:
            event = dl_module.ThreatEvent(
                timestamp="2024-01-01T00:00:00Z",
                tenant_id="test_tenant",
                category=dl_module.ThreatCategory.ANOMALY,
                severity=dl_module.ThreatSeverity.HIGH,
                source_ip=ip,
                source="test",
                description="Test event",
                details={},
                threat_score=score,
            )
            dl_module.record_threat_event(event)

        # Query with minimum score filter
        results = dl_module.query_threat_intelligence(
            min_score=0.5, tenant_id="test_tenant"
        )
        self.assertEqual(len(results), 2)
        # Should be ordered by score descending
        self.assertEqual(results[0].identifier, "10.0.0.3")
        self.assertEqual(results[1].identifier, "10.0.0.2")

        # Query specific IP
        results = dl_module.query_threat_intelligence(
            identifier="10.0.0.1", tenant_id="test_tenant"
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].identifier, "10.0.0.1")

    def test_hunt_threats_by_category(self):
        """Test threat hunting by category."""
        dl_module = self.reload_module_with_temp_db()

        # Create events with different categories
        categories = [
            dl_module.ThreatCategory.BOT_DETECTION,
            dl_module.ThreatCategory.HONEYPOT_HIT,
            dl_module.ThreatCategory.BOT_DETECTION,
        ]
        for i, cat in enumerate(categories):
            event = dl_module.ThreatEvent(
                timestamp=f"2024-01-01T00:00:0{i}Z",
                tenant_id="test_tenant",
                category=cat,
                severity=dl_module.ThreatSeverity.MEDIUM,
                source_ip=f"10.0.0.{i}",
                source="test",
                description=f"Event {i}",
                details={},
                threat_score=0.5,
            )
            dl_module.record_threat_event(event)

        # Hunt for bot detections
        results = dl_module.hunt_threats(
            category=dl_module.ThreatCategory.BOT_DETECTION, tenant_id="test_tenant"
        )
        self.assertEqual(len(results), 2)
        for result in results:
            self.assertEqual(result["category"], "bot_detection")

    def test_hunt_threats_by_time_range(self):
        """Test threat hunting with time range filters."""
        dl_module = self.reload_module_with_temp_db()

        # Create events at different times
        timestamps = [
            "2024-01-01T10:00:00Z",
            "2024-01-01T12:00:00Z",
            "2024-01-01T14:00:00Z",
        ]
        for i, ts in enumerate(timestamps):
            event = dl_module.ThreatEvent(
                timestamp=ts,
                tenant_id="test_tenant",
                category=dl_module.ThreatCategory.ANOMALY,
                severity=dl_module.ThreatSeverity.LOW,
                source_ip=f"10.0.0.{i}",
                source="test",
                description=f"Event {i}",
                details={},
                threat_score=0.3,
            )
            dl_module.record_threat_event(event)

        # Hunt within time range
        results = dl_module.hunt_threats(
            start_time="2024-01-01T11:00:00Z",
            end_time="2024-01-01T13:00:00Z",
            tenant_id="test_tenant",
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["timestamp"], "2024-01-01T12:00:00Z")

    def test_calculate_and_get_analytics_metrics(self):
        """Test storing and retrieving analytics metrics."""
        dl_module = self.reload_module_with_temp_db()

        # Store metrics
        dl_module.calculate_analytics_metric(
            "avg_threat_score", 0.75, metadata={"period": "1h", "sample_size": 100}
        )
        dl_module.calculate_analytics_metric("unique_ips", 42.0)

        # Retrieve all metrics
        results = dl_module.get_analytics_metrics()
        self.assertEqual(len(results), 2)

        # Retrieve specific metric
        results = dl_module.get_analytics_metrics(metric_name="avg_threat_score")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["metric_value"], 0.75)
        self.assertIsNotNone(results[0]["metadata"])

    def test_data_retention_policy(self):
        """Test data retention policy removes old records."""
        dl_module = self.reload_module_with_temp_db()

        # Create old and recent events
        old_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        recent_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

        old_event = dl_module.ThreatEvent(
            timestamp=old_date,
            tenant_id="test_tenant",
            category=dl_module.ThreatCategory.ANOMALY,
            severity=dl_module.ThreatSeverity.LOW,
            source_ip="192.168.1.1",
            source="test",
            description="Old event",
            details={},
            threat_score=0.2,
        )
        recent_event = dl_module.ThreatEvent(
            timestamp=recent_date,
            tenant_id="test_tenant",
            category=dl_module.ThreatCategory.ANOMALY,
            severity=dl_module.ThreatSeverity.LOW,
            source_ip="192.168.1.2",
            source="test",
            description="Recent event",
            details={},
            threat_score=0.2,
        )

        dl_module.record_threat_event(old_event)
        dl_module.record_threat_event(recent_event)

        # Apply retention policy (keep 90 days)
        deleted = dl_module.apply_data_retention_policy(retention_days=90)
        self.assertEqual(deleted, 1)

        # Verify only recent event remains
        conn = sqlite3.connect(self.temp_db)
        try:
            cursor = conn.execute("SELECT COUNT(*) as count FROM threat_events")
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)

            cursor = conn.execute("SELECT source_ip FROM threat_events")
            row = cursor.fetchone()
            self.assertEqual(row[0], "192.168.1.2")
        finally:
            conn.close()

    def test_governance_log(self):
        """Test governance logging functionality."""
        dl_module = self.reload_module_with_temp_db()

        # Apply retention policy to create a governance log entry
        dl_module.apply_data_retention_policy(retention_days=90)

        # Check governance log
        log_entries = dl_module.get_governance_log()
        self.assertGreater(len(log_entries), 0)
        self.assertEqual(log_entries[0]["action"], "data_retention_cleanup")
        self.assertIsNotNone(log_entries[0]["details"])

    def test_threat_statistics(self):
        """Test threat statistics calculation."""
        dl_module = self.reload_module_with_temp_db()

        # Create diverse events
        events_data = [
            (
                dl_module.ThreatCategory.BOT_DETECTION,
                dl_module.ThreatSeverity.HIGH,
                "10.0.0.1",
                0.9,
            ),
            (
                dl_module.ThreatCategory.BOT_DETECTION,
                dl_module.ThreatSeverity.MEDIUM,
                "10.0.0.2",
                0.6,
            ),
            (
                dl_module.ThreatCategory.HONEYPOT_HIT,
                dl_module.ThreatSeverity.HIGH,
                "10.0.0.3",
                0.8,
            ),
            (
                dl_module.ThreatCategory.ANOMALY,
                dl_module.ThreatSeverity.LOW,
                "10.0.0.1",
                0.3,
            ),
        ]

        for cat, sev, ip, score in events_data:
            event = dl_module.ThreatEvent(
                timestamp="2024-01-01T00:00:00Z",
                tenant_id="test_tenant",
                category=cat,
                severity=sev,
                source_ip=ip,
                source="test",
                description="Test event",
                details={},
                threat_score=score,
            )
            dl_module.record_threat_event(event)

        # Get statistics
        stats = dl_module.get_threat_statistics(tenant_id="test_tenant")
        self.assertEqual(stats["total_events"], 4)
        self.assertEqual(stats["by_category"]["bot_detection"], 2)
        self.assertEqual(stats["by_category"]["honeypot_hit"], 1)
        self.assertEqual(stats["by_severity"]["high"], 2)
        self.assertEqual(stats["by_severity"]["medium"], 1)
        self.assertGreater(len(stats["top_threats"]), 0)

    def test_multiple_categories_same_ip(self):
        """Test that multiple categories are tracked for the same IP."""
        dl_module = self.reload_module_with_temp_db()

        # Record different category events from same IP
        categories = [
            dl_module.ThreatCategory.BOT_DETECTION,
            dl_module.ThreatCategory.RATE_LIMIT_VIOLATION,
        ]

        for cat in categories:
            event = dl_module.ThreatEvent(
                timestamp="2024-01-01T00:00:00Z",
                tenant_id="test_tenant",
                category=cat,
                severity=dl_module.ThreatSeverity.MEDIUM,
                source_ip="10.0.0.100",
                source="test",
                description="Test",
                details={},
                threat_score=0.5,
            )
            dl_module.record_threat_event(event)

        # Query threat intelligence
        results = dl_module.query_threat_intelligence(
            identifier="10.0.0.100", tenant_id="test_tenant"
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0].categories), 2)
        self.assertIn("bot_detection", results[0].categories)
        self.assertIn("rate_limit_violation", results[0].categories)

    def test_hunt_threats_with_severity_filter(self):
        """Test threat hunting filtered by severity."""
        dl_module = self.reload_module_with_temp_db()

        # Create events with different severities
        severities = [
            dl_module.ThreatSeverity.CRITICAL,
            dl_module.ThreatSeverity.LOW,
            dl_module.ThreatSeverity.CRITICAL,
        ]

        for i, sev in enumerate(severities):
            event = dl_module.ThreatEvent(
                timestamp=f"2024-01-01T00:00:0{i}Z",
                tenant_id="test_tenant",
                category=dl_module.ThreatCategory.ATTACK_PATTERN,
                severity=sev,
                source_ip=f"10.0.0.{i}",
                source="test",
                description=f"Event {i}",
                details={},
                threat_score=0.7,
            )
            dl_module.record_threat_event(event)

        # Hunt for critical severity only
        results = dl_module.hunt_threats(
            severity=dl_module.ThreatSeverity.CRITICAL, tenant_id="test_tenant"
        )
        self.assertEqual(len(results), 2)
        for result in results:
            self.assertEqual(result["severity"], "critical")

    def test_threat_event_with_metadata(self):
        """Test recording threat event with optional metadata."""
        dl_module = self.reload_module_with_temp_db()

        event = dl_module.ThreatEvent(
            timestamp="2024-01-01T00:00:00Z",
            tenant_id="test_tenant",
            category=dl_module.ThreatCategory.WAF_TRIGGER,
            severity=dl_module.ThreatSeverity.HIGH,
            source_ip="192.168.1.50",
            source="waf_module",
            description="SQL injection attempt",
            details={"payload": "SELECT * FROM users"},
            threat_score=0.95,
            action_taken="blocked",
            metadata={"rule_id": "SQL001", "confidence": 0.99},
        )

        dl_module.record_threat_event(event)

        # Query and verify metadata
        results = dl_module.hunt_threats(
            source_ip="192.168.1.50", tenant_id="test_tenant"
        )
        self.assertEqual(len(results), 1)
        self.assertIsNotNone(results[0]["metadata"])
        self.assertEqual(results[0]["metadata"]["rule_id"], "SQL001")


if __name__ == "__main__":
    unittest.main()
