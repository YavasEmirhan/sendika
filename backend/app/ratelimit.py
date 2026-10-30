"""Basit, süreç içi kayan pencere hız sınırlayıcı.

Pilot tek süreçte çalışır. Birden fazla süreç/sunucuya geçildiğinde Redis gibi
paylaşılan bir depoya taşınmalıdır. IP adresleri saklanmaz; yalnızca
bellekte, tuzlanmış özet olarak anahtar oluşturulur.
"""
import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_SALT = secrets.token_bytes(16)  # her açılışta yenilenir


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window_seconds:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def client_key(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    return hashlib.sha256(_SALT + ip.encode()).hexdigest()[:24]


def enforce(request: Request, bucket: str, limit: int, window_seconds: int) -> None:
    if not limiter.hit(f"{bucket}:{client_key(request)}", limit, window_seconds):
        raise HTTPException(
            status_code=429,
            detail="Çok fazla deneme yapıldı. Lütfen birkaç dakika sonra tekrar deneyin.",
        )
