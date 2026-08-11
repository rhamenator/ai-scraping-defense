"""Selectable durable security-event storage and export helpers."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, Protocol

DEFAULT_DB_DIR = "/app/data"
DB_PATH = os.getenv(
    "SECURITY_EVENTS_DB_PATH",
    os.path.join(DEFAULT_DB_DIR, "security_events.db"),
)
MAX_EXPORT_EVENTS = 100_000

logger = logging.getLogger(__name__)

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS security_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT,
    source TEXT,
    severity TEXT NOT NULL,
    ip TEXT,
    path TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_security_events_created_at
    ON security_events (created_at);
CREATE INDEX IF NOT EXISTS idx_security_events_type
    ON security_events (event_type);
CREATE INDEX IF NOT EXISTS idx_security_events_source
    ON security_events (source);
"""

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS security_events (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT,
    source TEXT,
    severity TEXT NOT NULL,
    ip TEXT,
    path TEXT,
    payload_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_security_events_created_at
    ON security_events (created_at);
CREATE INDEX IF NOT EXISTS idx_security_events_type
    ON security_events (event_type);
CREATE INDEX IF NOT EXISTS idx_security_events_source
    ON security_events (source);
"""

IP_FIELD_NAMES = {
    "client_ip",
    "forwarded_for",
    "ip",
    "ip_address",
    "remote_ip",
    "source_ip",
}
PATH_FIELD_NAMES = {"path", "request_path", "route"}
SENSITIVE_FIELD_TOKENS = (
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
    "webhook",
)


class SecurityEventStore(Protocol):
    """Storage contract shared by the supported audit backends."""

    backend_name: str

    def validate(self) -> None: ...

    def record(self, event: dict[str, Any]) -> int: ...

    def load(self, *, limit: int, event_type: str | None) -> list[dict[str, Any]]: ...


def _is_sensitive_field(field_name: str | None) -> bool:
    if not field_name:
        return False
    normalized = field_name.lower()
    return any(token in normalized for token in SENSITIVE_FIELD_TOKENS)


def redact_sensitive_data(value: Any, field_name: str | None = None) -> Any:
    """Redact secrets while preserving enough structure for investigation."""
    if isinstance(value, dict):
        return {key: redact_sensitive_data(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_data(item, field_name) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive_data(item, field_name) for item in value]
    if field_name and field_name.lower() in IP_FIELD_NAMES:
        return "[REDACTED_IP]"
    if _is_sensitive_field(field_name):
        return "<redacted>"
    return value


def _extract_first(payload: dict[str, Any], field_names: Iterable[str]) -> str | None:
    for field_name in field_names:
        value = payload.get(field_name)
        if isinstance(value, str) and value:
            return value
    return None


def _normalize_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("security event limit must be an integer")
    if limit < 1 or limit > MAX_EXPORT_EVENTS:
        raise ValueError(
            f"security event limit must be between 1 and {MAX_EXPORT_EVENTS}"
        )
    return limit


def _event_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    payload = row[9] or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    created_at = row[1]
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    return {
        "id": row[0],
        "created_at": created_at,
        "event_type": row[2],
        "actor": row[3],
        "action": row[4],
        "source": row[5],
        "severity": row[6],
        "ip": row[7],
        "path": row[8],
        "payload": payload,
    }


class SQLiteSecurityEventStore:
    backend_name = "sqlite"

    def __init__(self, db_path: str) -> None:
        self.db_path = self._prepare_path(db_path)

    @staticmethod
    def _prepare_path(db_path: str) -> str:
        directory = os.path.dirname(db_path) or "."
        try:
            os.makedirs(directory, exist_ok=True)
            return db_path
        except OSError as exc:
            fallback = os.path.join(tempfile.gettempdir(), "security_events.db")
            logger.warning(
                "Cannot create security event DB in %s: %s. Using %s.",
                db_path,
                exc,
                fallback,
            )
            os.makedirs(os.path.dirname(fallback), exist_ok=True)
            return fallback

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SQLITE_SCHEMA)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def record(self, event: dict[str, Any]) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO security_events (
                    created_at, event_type, actor, action, source, severity,
                    ip, path, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["created_at"],
                    event["event_type"],
                    event["actor"],
                    event["action"],
                    event["source"],
                    event["severity"],
                    event["ip"],
                    event["path"],
                    json.dumps(event["payload"], sort_keys=True, default=str),
                ),
            )
            return int(cursor.lastrowid)

    def validate(self) -> None:
        """Create the schema now so path and permission errors fail startup."""
        with self._connect():
            pass

    def load(self, *, limit: int, event_type: str | None) -> list[dict[str, Any]]:
        query = """
            SELECT id, created_at, event_type, actor, action, source,
                   severity, ip, path, payload_json
            FROM security_events
        """
        parameters: list[Any] = []
        if event_type:
            query += " WHERE event_type = ?"
            parameters.append(event_type)
        query += " ORDER BY id DESC LIMIT ?"
        parameters.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, parameters).fetchall()
        return [_event_from_row(row) for row in reversed(rows)]


class PostgresSecurityEventStore:
    backend_name = "postgres"

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn
        self.connect_kwargs = self._connection_kwargs() if dsn is None else {}

    @staticmethod
    def _connection_kwargs() -> dict[str, Any]:
        password = os.getenv("SECURITY_EVENTS_PG_PASSWORD") or os.getenv("PG_PASSWORD")
        password_file = os.getenv("SECURITY_EVENTS_PG_PASSWORD_FILE") or os.getenv(
            "PG_PASSWORD_FILE"
        )
        if password_file:
            password = Path(password_file).read_text(encoding="utf-8").strip()
        try:
            port = int(
                os.getenv("SECURITY_EVENTS_PG_PORT", os.getenv("PG_PORT", "5432"))
            )
        except ValueError as exc:
            raise ValueError(
                "security event PostgreSQL port must be an integer"
            ) from exc
        return {
            "host": os.getenv(
                "SECURITY_EVENTS_PG_HOST", os.getenv("PG_HOST", "postgres")
            ),
            "port": port,
            "dbname": os.getenv(
                "SECURITY_EVENTS_PG_DBNAME", os.getenv("PG_DBNAME", "markovdb")
            ),
            "user": os.getenv(
                "SECURITY_EVENTS_PG_USER", os.getenv("PG_USER", "markovuser")
            ),
            "password": password,
            "connect_timeout": 5,
        }

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        try:
            import psycopg2
        except (
            ImportError
        ) as exc:  # pragma: no cover - dependency is required in releases
            raise RuntimeError(
                "PostgreSQL audit storage requires the psycopg2 package"
            ) from exc
        conn = (
            psycopg2.connect(self.dsn, connect_timeout=5)
            if self.dsn
            else psycopg2.connect(**self.connect_kwargs)
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute(POSTGRES_SCHEMA)
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def record(self, event: dict[str, Any]) -> int:
        from psycopg2.extras import Json

        with self._connect() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO security_events (
                    created_at, event_type, actor, action, source, severity,
                    ip, path, payload_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    event["created_at"],
                    event["event_type"],
                    event["actor"],
                    event["action"],
                    event["source"],
                    event["severity"],
                    event["ip"],
                    event["path"],
                    Json(event["payload"]),
                ),
            )
            return int(cursor.fetchone()[0])

    def validate(self) -> None:
        """Connect and create the schema now instead of failing on the first event."""
        with self._connect():
            pass

    def load(self, *, limit: int, event_type: str | None) -> list[dict[str, Any]]:
        query = """
            SELECT id, created_at, event_type, actor, action, source,
                   severity, ip, path, payload_json
            FROM security_events
        """
        parameters: list[Any] = []
        if event_type:
            query += " WHERE event_type = %s"
            parameters.append(event_type)
        query += " ORDER BY id DESC LIMIT %s"
        parameters.append(limit)
        with self._connect() as conn, conn.cursor() as cursor:
            cursor.execute(query, parameters)
            rows = cursor.fetchall()
        return [_event_from_row(row) for row in reversed(rows)]


def _create_store() -> SecurityEventStore:
    backend = (
        os.getenv(
            "AUDIT_STORAGE_BACKEND", os.getenv("SECURITY_EVENTS_BACKEND", "sqlite")
        )
        .strip()
        .lower()
    )
    if backend == "sqlite":
        store = SQLiteSecurityEventStore(DB_PATH)
        store.validate()
        globals()["DB_PATH"] = store.db_path
        return store
    if backend in {"postgres", "postgresql"}:
        dsn = os.getenv("SECURITY_EVENTS_POSTGRES_DSN")
        store = PostgresSecurityEventStore(dsn)
        store.validate()
        return store
    raise ValueError("AUDIT_STORAGE_BACKEND must be one of: sqlite, postgres")


_STORE = _create_store()


def audit_storage_backend() -> str:
    """Return the active backend name for health and diagnostics."""
    return _STORE.backend_name


def record_security_event(
    event_type: str,
    *,
    actor: str = "system",
    action: str | None = None,
    source: str | None = None,
    severity: str = "info",
    payload: Optional[dict[str, Any]] = None,
    created_at: str | None = None,
) -> int:
    """Persist a structured security event and return its backend row id."""
    event_payload = redact_sensitive_data(payload or {})
    event = {
        "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "actor": actor,
        "action": action,
        "source": source,
        "severity": severity,
        "ip": _extract_first(event_payload, IP_FIELD_NAMES),
        "path": _extract_first(event_payload, PATH_FIELD_NAMES),
        "payload": event_payload,
    }
    return _STORE.record(event)


def load_security_events(
    *, limit: int = 1000, event_type: str | None = None
) -> list[dict[str, Any]]:
    """Load stored security events in oldest-to-newest export order."""
    return _STORE.load(limit=_normalize_limit(limit), event_type=event_type)


def export_security_events(
    *,
    output_path: str | None = None,
    limit: int = 1000,
    event_type: str | None = None,
) -> tuple[int, str]:
    """Export events as JSONL and optionally write them to disk."""
    events = load_security_events(limit=limit, event_type=event_type)
    jsonl = "\n".join(json.dumps(event, sort_keys=True) for event in events)
    if jsonl:
        jsonl += "\n"
    if output_path:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(jsonl, encoding="utf-8")
        try:
            os.chmod(destination, 0o600)
        except OSError:
            logger.debug(
                "Unable to set restrictive permissions on %s",
                destination,
                exc_info=True,
            )
    return len(events), jsonl
