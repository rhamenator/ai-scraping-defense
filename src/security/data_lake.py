"""Security Data Lake for threat intelligence and analytics.

This module provides a centralized data lake for collecting, storing, and
analyzing security-related events across the AI scraping defense system.
It supports threat intelligence aggregation, threat hunting queries, and
data governance with configurable retention policies.

Key features:
- Threat intelligence collection from multiple sources
- Security event aggregation and storage
- Query interface for threat hunting
- Data retention and governance policies
- Integration with Redis for caching and SQLite for persistence
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from src.shared.config import CONFIG

logger = logging.getLogger(__name__)

# Configuration
DEFAULT_DATA_LAKE_DIR = "/app/data/security"
FALLBACK_DATA_LAKE_DIR = "/tmp/security_data_lake"

# Use fallback directory if default doesn't exist and can't be created
_default_path = os.path.join(DEFAULT_DATA_LAKE_DIR, "security_data_lake.db")
_fallback_path = os.path.join(FALLBACK_DATA_LAKE_DIR, "security_data_lake.db")

# Allow override via environment variable, otherwise determine best path
if os.getenv("SECURITY_DATA_LAKE_PATH"):
    DATA_LAKE_DB_PATH = os.getenv("SECURITY_DATA_LAKE_PATH")
else:
    # Try to use default, fall back to /tmp if not accessible
    try:
        os.makedirs(DEFAULT_DATA_LAKE_DIR, exist_ok=True)
        DATA_LAKE_DB_PATH = _default_path
    except (OSError, PermissionError):
        DATA_LAKE_DB_PATH = _fallback_path

# Data retention configuration (days)
DEFAULT_RETENTION_DAYS = int(os.getenv("SECURITY_DATA_RETENTION_DAYS", "90"))


class ThreatCategory(str, Enum):
    """Categories of security threats tracked in the data lake."""

    BOT_DETECTION = "bot_detection"
    ANOMALY = "anomaly"
    ATTACK_PATTERN = "attack_pattern"
    IP_REPUTATION = "ip_reputation"
    HONEYPOT_HIT = "honeypot_hit"
    RATE_LIMIT_VIOLATION = "rate_limit_violation"
    AUTHENTICATION_FAILURE = "authentication_failure"
    WAF_TRIGGER = "waf_trigger"
    UNKNOWN = "unknown"


class ThreatSeverity(str, Enum):
    """Severity levels for threat events."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class ThreatEvent:
    """Represents a security threat event in the data lake."""

    timestamp: str
    tenant_id: str
    category: ThreatCategory
    severity: ThreatSeverity
    source_ip: str
    source: str  # Service/component that generated the event
    description: str
    details: dict[str, Any]
    threat_score: float = 0.0
    action_taken: str = "none"
    metadata: dict[str, Any] | None = None


@dataclass
class ThreatIntelligence:
    """Aggregated threat intelligence for an IP or pattern."""

    identifier: str  # IP address or pattern hash
    identifier_type: str  # 'ip', 'pattern', 'signature'
    threat_score: float
    first_seen: str
    last_seen: str
    event_count: int
    categories: list[str]
    tenant_id: str


# Ensure the directory for the database exists
try:
    db_dir = os.path.dirname(DATA_LAKE_DB_PATH)
    if db_dir:  # Only try to create if there's a directory path
        os.makedirs(db_dir, exist_ok=True)
except (OSError, PermissionError) as e:
    logger.warning("Could not create data lake directory, using fallback: %s", e)

# Database schema
SCHEMA = """
-- Main threat events table
CREATE TABLE IF NOT EXISTS threat_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    source_ip TEXT,
    source TEXT NOT NULL,
    description TEXT,
    details TEXT,
    threat_score REAL,
    action_taken TEXT,
    metadata TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Aggregated threat intelligence table
CREATE TABLE IF NOT EXISTS threat_intelligence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identifier TEXT NOT NULL,
    identifier_type TEXT NOT NULL,
    threat_score REAL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    event_count INTEGER DEFAULT 1,
    categories TEXT,
    tenant_id TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(identifier, identifier_type, tenant_id)
);

-- Security analytics metadata
CREATE TABLE IF NOT EXISTS analytics_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT NOT NULL,
    metric_value REAL,
    calculation_time TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    metadata TEXT
);

-- Data governance log
CREATE TABLE IF NOT EXISTS governance_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    records_affected INTEGER,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    details TEXT
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_threat_events_timestamp ON threat_events (timestamp);
CREATE INDEX IF NOT EXISTS idx_threat_events_tenant ON threat_events (tenant_id);
CREATE INDEX IF NOT EXISTS idx_threat_events_source_ip ON threat_events (source_ip);
CREATE INDEX IF NOT EXISTS idx_threat_events_category ON threat_events (category);
CREATE INDEX IF NOT EXISTS idx_threat_intel_identifier ON threat_intelligence (identifier, tenant_id);
CREATE INDEX IF NOT EXISTS idx_threat_intel_score ON threat_intelligence (threat_score);
"""


@contextmanager
def get_data_lake_conn():
    """Context manager for database connections."""
    conn = sqlite3.connect(DATA_LAKE_DB_PATH)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("Database transaction failed: %s", e)
        raise
    finally:
        conn.close()


def record_threat_event(event: ThreatEvent) -> None:
    """Record a threat event in the data lake.

    Args:
        event: ThreatEvent instance to record
    """
    with get_data_lake_conn() as conn:
        conn.execute(
            """
            INSERT INTO threat_events (
                timestamp, tenant_id, category, severity, source_ip,
                source, description, details, threat_score, action_taken, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.timestamp,
                event.tenant_id,
                event.category.value,
                event.severity.value,
                event.source_ip,
                event.source,
                event.description,
                json.dumps(event.details),
                event.threat_score,
                event.action_taken,
                json.dumps(event.metadata) if event.metadata else None,
            ),
        )
        logger.debug(
            "Recorded threat event: %s from %s (score: %.2f)",
            event.category,
            event.source_ip,
            event.threat_score,
        )

    # Update threat intelligence aggregation
    _update_threat_intelligence(event)


def _update_threat_intelligence(event: ThreatEvent) -> None:
    """Update aggregated threat intelligence based on a new event.

    Args:
        event: ThreatEvent that triggered the update
    """
    with get_data_lake_conn() as conn:
        # Check if intelligence record exists
        cursor = conn.execute(
            """
            SELECT id, event_count, threat_score, categories, first_seen
            FROM threat_intelligence
            WHERE identifier = ? AND identifier_type = 'ip' AND tenant_id = ?
            """,
            (event.source_ip, event.tenant_id),
        )
        row = cursor.fetchone()

        if row:
            # Update existing record
            categories = json.loads(row["categories"])
            if event.category.value not in categories:
                categories.append(event.category.value)

            new_count = row["event_count"] + 1
            # Calculate weighted average of threat scores
            new_score = (
                row["threat_score"] * row["event_count"] + event.threat_score
            ) / new_count

            conn.execute(
                """
                UPDATE threat_intelligence
                SET last_seen = ?, event_count = ?, threat_score = ?,
                    categories = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    event.timestamp,
                    new_count,
                    new_score,
                    json.dumps(categories),
                    row["id"],
                ),
            )
        else:
            # Insert new record
            conn.execute(
                """
                INSERT INTO threat_intelligence (
                    identifier, identifier_type, threat_score, first_seen,
                    last_seen, event_count, categories, tenant_id
                ) VALUES (?, 'ip', ?, ?, ?, 1, ?, ?)
                """,
                (
                    event.source_ip,
                    event.threat_score,
                    event.timestamp,
                    event.timestamp,
                    json.dumps([event.category.value]),
                    event.tenant_id,
                ),
            )


def query_threat_intelligence(
    identifier: Optional[str] = None,
    min_score: float = 0.0,
    tenant_id: Optional[str] = None,
    limit: int = 100,
) -> list[ThreatIntelligence]:
    """Query aggregated threat intelligence.

    Args:
        identifier: Optional IP or pattern to filter by
        min_score: Minimum threat score threshold
        tenant_id: Optional tenant filter
        limit: Maximum number of results to return

    Returns:
        List of ThreatIntelligence objects
    """
    tid = tenant_id or CONFIG.TENANT_ID
    with get_data_lake_conn() as conn:
        query = """
            SELECT identifier, identifier_type, threat_score, first_seen,
                   last_seen, event_count, categories, tenant_id
            FROM threat_intelligence
            WHERE tenant_id = ? AND threat_score >= ?
        """
        params: list[Any] = [tid, min_score]

        if identifier:
            query += " AND identifier = ?"
            params.append(identifier)

        query += " ORDER BY threat_score DESC, last_seen DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, params)
        results = []
        for row in cursor.fetchall():
            results.append(
                ThreatIntelligence(
                    identifier=row["identifier"],
                    identifier_type=row["identifier_type"],
                    threat_score=row["threat_score"],
                    first_seen=row["first_seen"],
                    last_seen=row["last_seen"],
                    event_count=row["event_count"],
                    categories=json.loads(row["categories"]),
                    tenant_id=row["tenant_id"],
                )
            )
        return results


def hunt_threats(
    category: Optional[ThreatCategory] = None,
    severity: Optional[ThreatSeverity] = None,
    source_ip: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    min_score: float = 0.0,
    tenant_id: Optional[str] = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Hunt for threats using flexible query parameters.

    Args:
        category: Filter by threat category
        severity: Filter by severity level
        source_ip: Filter by source IP
        start_time: Start timestamp (ISO format)
        end_time: End timestamp (ISO format)
        min_score: Minimum threat score
        tenant_id: Optional tenant filter
        limit: Maximum results to return

    Returns:
        List of threat event dictionaries
    """
    tid = tenant_id or CONFIG.TENANT_ID
    with get_data_lake_conn() as conn:
        query = "SELECT * FROM threat_events WHERE tenant_id = ? AND threat_score >= ?"
        params: list[Any] = [tid, min_score]

        if category:
            query += " AND category = ?"
            params.append(category.value)

        if severity:
            query += " AND severity = ?"
            params.append(severity.value)

        if source_ip:
            query += " AND source_ip = ?"
            params.append(source_ip)

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)

        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, params)
        results = []
        for row in cursor.fetchall():
            event_dict = dict(row)
            # Parse JSON fields
            if event_dict.get("details"):
                event_dict["details"] = json.loads(event_dict["details"])
            if event_dict.get("metadata"):
                event_dict["metadata"] = json.loads(event_dict["metadata"])
            results.append(event_dict)
        return results


def calculate_analytics_metric(
    metric_name: str, metric_value: float, metadata: Optional[dict[str, Any]] = None
) -> None:
    """Store a calculated analytics metric.

    Args:
        metric_name: Name of the metric
        metric_value: Calculated value
        metadata: Optional additional context
    """
    tid = CONFIG.TENANT_ID
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with get_data_lake_conn() as conn:
        conn.execute(
            """
            INSERT INTO analytics_metadata (metric_name, metric_value, calculation_time, tenant_id, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                metric_name,
                metric_value,
                timestamp,
                tid,
                json.dumps(metadata) if metadata else None,
            ),
        )


def get_analytics_metrics(
    metric_name: Optional[str] = None, limit: int = 100
) -> list[dict[str, Any]]:
    """Retrieve analytics metrics.

    Args:
        metric_name: Optional filter by metric name
        limit: Maximum results to return

    Returns:
        List of metric dictionaries
    """
    with get_data_lake_conn() as conn:
        query = "SELECT * FROM analytics_metadata"
        params: list[Any] = []

        if metric_name:
            query += " WHERE metric_name = ?"
            params.append(metric_name)

        query += " ORDER BY calculation_time DESC LIMIT ?"
        params.append(limit)

        cursor = conn.execute(query, params)
        results = []
        for row in cursor.fetchall():
            metric_dict = dict(row)
            if metric_dict.get("metadata"):
                metric_dict["metadata"] = json.loads(metric_dict["metadata"])
            results.append(metric_dict)
        return results


def apply_data_retention_policy(retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
    """Apply data retention policy by removing old records.

    Args:
        retention_days: Number of days to retain data

    Returns:
        Number of records deleted
    """
    cutoff_date = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=retention_days)
    ).isoformat()

    with get_data_lake_conn() as conn:
        # Delete old threat events
        cursor = conn.execute(
            "DELETE FROM threat_events WHERE timestamp < ?", (cutoff_date,)
        )
        deleted_count = cursor.rowcount

        # Log governance action
        conn.execute(
            """
            INSERT INTO governance_log (action, records_affected, details)
            VALUES (?, ?, ?)
            """,
            (
                "data_retention_cleanup",
                deleted_count,
                json.dumps(
                    {"retention_days": retention_days, "cutoff_date": cutoff_date}
                ),
            ),
        )

        logger.info(
            "Data retention policy applied: deleted %d records older than %d days",
            deleted_count,
            retention_days,
        )
        return deleted_count


def get_governance_log(limit: int = 100) -> list[dict[str, Any]]:
    """Retrieve data governance audit log.

    Args:
        limit: Maximum results to return

    Returns:
        List of governance log entries
    """
    with get_data_lake_conn() as conn:
        cursor = conn.execute(
            "SELECT * FROM governance_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        results = []
        for row in cursor.fetchall():
            log_entry = dict(row)
            if log_entry.get("details"):
                log_entry["details"] = json.loads(log_entry["details"])
            results.append(log_entry)
        return results


def get_threat_statistics(tenant_id: Optional[str] = None) -> dict[str, Any]:
    """Get summary statistics for threats in the data lake.

    Args:
        tenant_id: Optional tenant filter

    Returns:
        Dictionary with threat statistics
    """
    tid = tenant_id or CONFIG.TENANT_ID
    with get_data_lake_conn() as conn:
        # Total events
        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM threat_events WHERE tenant_id = ?", (tid,)
        )
        total_events = cursor.fetchone()["count"]

        # Events by category
        cursor = conn.execute(
            """
            SELECT category, COUNT(*) as count
            FROM threat_events
            WHERE tenant_id = ?
            GROUP BY category
            """,
            (tid,),
        )
        by_category = {row["category"]: row["count"] for row in cursor.fetchall()}

        # Events by severity
        cursor = conn.execute(
            """
            SELECT severity, COUNT(*) as count
            FROM threat_events
            WHERE tenant_id = ?
            GROUP BY severity
            """,
            (tid,),
        )
        by_severity = {row["severity"]: row["count"] for row in cursor.fetchall()}

        # Top threat IPs
        cursor = conn.execute(
            """
            SELECT identifier, threat_score, event_count
            FROM threat_intelligence
            WHERE tenant_id = ?
            ORDER BY threat_score DESC
            LIMIT 10
            """,
            (tid,),
        )
        top_threats = [
            {
                "ip": row["identifier"],
                "score": row["threat_score"],
                "events": row["event_count"],
            }
            for row in cursor.fetchall()
        ]

        return {
            "total_events": total_events,
            "by_category": by_category,
            "by_severity": by_severity,
            "top_threats": top_threats,
            "tenant_id": tid,
        }
