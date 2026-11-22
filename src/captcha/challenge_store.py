"""Server-side CAPTCHA challenges and rate counters (#1903).

A challenge is a random id that maps, on the server, to the answer and the client it was issued to. The id reveals
nothing, and ``take`` consumes it atomically, so a challenge can be answered once. Redis is used when it is reachable;
otherwise state lives in this process (correct for a single worker or replica only, and the health check says so).
"""

import json
import logging
import os
import threading
import time
from typing import Any, Optional

from src.shared.config import tenant_key
from src.shared.redis_client import get_redis_connection

logger = logging.getLogger(__name__)


class ChallengeStore:
    def __init__(self, backend: Optional[str] = None):
        self._mode = (backend or os.getenv("CAPTCHA_STORE", "auto")).lower()
        self._memory: dict[str, tuple[float, str]] = {}
        self._counters: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()
        self._redis: Any = None
        self._redis_tried = False

    # -- backend selection -------------------------------------------------------------------------------------
    def _client(self) -> Any:
        if self._mode == "memory":
            return None
        if not self._redis_tried:
            self._redis_tried = True
            try:
                self._redis = get_redis_connection()
            except Exception as exc:  # noqa: BLE001 - any failure means "use the process-local store"
                logger.warning("CAPTCHA store: Redis unavailable (%s); using process memory", exc)
        return self._redis

    @property
    def backend(self) -> str:
        return "redis" if self._client() is not None else "memory"

    @staticmethod
    def _key(kind: str, name: str) -> str:
        return tenant_key(f"captcha:{kind}:{name}")

    # -- challenges --------------------------------------------------------------------------------------------
    def put(self, challenge_id: str, record: dict, ttl: int) -> None:
        payload = json.dumps(record, separators=(",", ":"))
        redis = self._client()
        if redis is not None:
            redis.set(self._key("c", challenge_id), payload, ex=ttl)
            return
        with self._lock:
            self._purge()
            self._memory[challenge_id] = (time.monotonic() + ttl, payload)

    def take(self, challenge_id: str) -> Optional[dict]:
        """Return and delete a challenge in one atomic step; None if unknown, expired or already used."""
        redis = self._client()
        if redis is not None:
            pipe = redis.pipeline(transaction=True)
            pipe.get(self._key("c", challenge_id))
            pipe.delete(self._key("c", challenge_id))
            raw = pipe.execute()[0]
        else:
            with self._lock:
                expires, raw = self._memory.pop(challenge_id, (0.0, None))
                if raw is not None and expires < time.monotonic():
                    raw = None
        if raw is None:
            return None
        return json.loads(raw.decode() if isinstance(raw, bytes) else raw)

    # -- rate limiting -----------------------------------------------------------------------------------------
    def allow(self, bucket: str, limit: int, window: int = 60) -> bool:
        """Count one event in ``bucket``; False once more than ``limit`` happened in the current window."""
        if limit <= 0:
            return True
        redis = self._client()
        if redis is not None:
            key = self._key("r", bucket)
            pipe = redis.pipeline(transaction=True)
            pipe.incr(key)
            pipe.expire(key, window, nx=True)
            return int(pipe.execute()[0]) <= limit
        now = time.monotonic()
        with self._lock:
            reset, count = self._counters.get(bucket, (0.0, 0))
            if reset < now:
                reset, count = now + window, 0
            self._counters[bucket] = (reset, count + 1)
            if len(self._counters) > 10000:
                self._counters = {k: v for k, v in self._counters.items() if v[0] >= now}
            return count + 1 <= limit

    def _purge(self) -> None:
        now = time.monotonic()
        if len(self._memory) > 10000:
            self._memory = {k: v for k, v in self._memory.items() if v[0] >= now}
