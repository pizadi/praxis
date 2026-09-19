"""Token-related helpers.

Refresh tokens are tracked in the DB (`refresh_tokens` table): a jti per
token, revoked on rotation/logout/deactivation. Access tokens are
short-lived and validated against the per-request `is_active`/`deleted_at`
check in `api/deps.py`, so they may stay valid for up to their full TTL
(30 minutes) after logout — an accepted trade-off, documented in
docs/auth.md.
"""

from __future__ import annotations

import datetime as dt


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)
