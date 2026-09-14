"""Persistent user cache for revoked/deleted users.

Access tokens are short-lived; refresh tokens carry a jti that we track so that
deleting a user or explicitly logging out invalidates outstanding refresh
tokens. For a single-doctor office scale this is a simple DB table.

The volatile-memory cache is intentionally small: a set of revoked access
token jti values with TTL == access token lifetime. Process-local, best
effort. The refresh token table is authoritative for refresh tokens.
"""

from __future__ import annotations

import datetime as dt
import threading
import time


class TokenCache:
    def __init__(self) -> None:
        self._revoked_access: dict[str, float] = {}
        self._lock = threading.Lock()

    def revoke_access(self, jti: str) -> None:
        with self._lock:
            self._revoked_access[jti] = time.monotonic()

    def is_access_revoked(self, jti: str) -> bool:
        with self._lock:
            return jti in self._revoked_access

    def cleanup(self, access_ttl_seconds: int) -> None:
        cutoff = time.monotonic() - access_ttl_seconds
        with self._lock:
            self._revoked_access = {
                j: t for j, t in self._revoked_access.items() if t > cutoff
            }


token_cache = TokenCache()


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
