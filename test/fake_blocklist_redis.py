"""A small dict-backed stand-in for the Redis commands the blocklist code uses (no fakeredis dependency)."""

import fnmatch
import time


class FakeBlocklistRedis:
    def __init__(self):
        self.data: dict[str, object] = {}
        self.expires: dict[str, float] = {}
        self.fail_with: Exception | None = None

    def _check(self):
        if self.fail_with:
            raise self.fail_with
        now = time.monotonic()
        for key in [k for k, at in self.expires.items() if at <= now]:
            self.data.pop(key, None)
            self.expires.pop(key, None)

    def set(self, key, value, ex=None):
        self._check()
        self.data[key] = value
        if ex is None:
            self.expires.pop(key, None)
        else:
            self.expires[key] = time.monotonic() + ex
        return True

    def setex(self, key, seconds, value):
        return self.set(key, value, ex=seconds)

    def get(self, key):
        self._check()
        value = self.data.get(key)
        return value if isinstance(value, str) else None

    def exists(self, *keys):
        self._check()
        return sum(1 for key in keys if key in self.data)

    def delete(self, *keys):
        self._check()
        removed = 0
        for key in keys:
            removed += self.data.pop(key, None) is not None
            self.expires.pop(key, None)
        return removed

    def ttl(self, key):
        self._check()
        if key not in self.data:
            return -2
        return -1 if key not in self.expires else max(0, int(self.expires[key] - time.monotonic()))

    def sadd(self, key, *members):
        self._check()
        self.data.setdefault(key, set()).add(*members)
        return len(members)

    def srem(self, key, *members):
        self._check()
        members_set = self.data.get(key)
        if not isinstance(members_set, set):
            return 0
        before = len(members_set)
        members_set.difference_update(members)
        if not members_set:
            self.data.pop(key, None)
        return before - len(members_set)

    def smembers(self, key):
        self._check()
        value = self.data.get(key)
        return set(value) if isinstance(value, set) else set()

    def scan_iter(self, match="*", count=None):
        self._check()
        return iter([k for k in list(self.data) if fnmatch.fnmatchcase(k, match)])

    def ping(self):
        self._check()
        return True
