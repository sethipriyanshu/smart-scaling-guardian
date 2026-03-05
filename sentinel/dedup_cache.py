"""
In-memory deduplication cache for Kubernetes events.
Key: (event UID, resourceVersion). TTL configurable (default 5 minutes).
"""
import time
import threading


class DedupCache:
    def __init__(self, ttl_seconds: int = 300):
        self._ttl = ttl_seconds
        self._cache: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()

    def seen(self, uid: str, resource_version: str) -> bool:
        """Return True if (uid, resource_version) was seen within TTL."""
        key = (uid, resource_version)
        with self._lock:
            self._evict_expired()
            if key in self._cache:
                return True
            self._cache[key] = time.monotonic()
            return False

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, t in self._cache.items() if now - t > self._ttl]
        for k in expired:
            del self._cache[k]
