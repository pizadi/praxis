# Auth & sessions

## Credentials

- Passwords: **argon2** (`passlib`), verified per login. User create/update
  enforce length 8–128 only (no complexity rule — LAN app).
- Login is identical-error for unknown user and wrong password, and verifies
  a throwaway hash when the user does not exist, so response **timing cannot
  enumerate usernames**.
- Login attempts (username, success, IP) are recorded in `login_audit`
  regardless of outcome.

## Brute-force lockout

- After `LOGIN_MAX_FAILURES` (default 5) failed logins **for one username**
  within `LOGIN_LOCK_MINUTES` (default 15), the account returns **429
  `login_locked`** for the rest of the window — even for the correct
  password. The window is rolling; no manual unlock.
- Deliberately **per-username, not per-IP**: behind the nginx proxy every
  request shares the proxy address, so IP-based counting would let one
  attacker lock out all users.
- Lockout state lives in `login_audit` (no extra table, no RAM state).

## Tokens

- JWT HS256. Access token 30 min, refresh token 7 days (`ACCESS_TOKEN_*` /
  `REFRESH_TOKEN_*`). Access-token claims: `sub`, `type`, `iat`, `exp`,
  `jti`, `role` (the role claim is informational — authorization always
  re-reads the DB role).
- Refresh tokens are single-use: every `/auth/refresh` rotates (old jti
  revoked, new one issued). Reusing a rotated token → 401; the newest token
  stays valid (no token-family revocation — accepted at this scale).
- `POST /auth/logout` revokes exactly the presented refresh token
  (token-possession based, unauthenticated) and writes an `audit_log` row
  (action `logout`, entity `session`).

## Revocation semantics

- **Deactivation / deletion**: enforced immediately — every request re-checks
  `is_active` / `deleted_at` on the user row; deactivation and deletion also
  revoke all outstanding refresh tokens.
- **Password change** (`PATCH /users/{id}`): revokes all of that user's
  outstanding refresh tokens; access tokens already issued stay valid up to
  their **30-minute TTL** — an accepted trade-off (same window applies after
  logout).
- UI logout calls `POST /auth/logout` best-effort, then clears localStorage
  (`clinic.access` / `clinic.refresh` / `clinic.user`).

## Rate-limit configuration

- `LOGIN_MAX_FAILURES`, `LOGIN_LOCK_MINUTES` — see `.env.example`.
