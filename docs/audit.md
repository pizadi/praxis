# Audit trail

Every mutating action (create / update / delete / restore / purge) is
recorded in the `audit_log` table before the endpoint returns:

- acting user (or `system` for automatic maintenance, e.g. the uploads
  purge), timestamp (timestamptz), action, entity type + id
- a human summary — e.g. "name surname (national-id)", "old → new" for
  renames, "ویزیت — 1500000" for payments (description first, then the raw
  amount)
- a JSON `details` payload with field-level diffs (old/new name, backup
  import summaries, purge counts…)
- the client IP — resolved as the leftmost `X-Forwarded-For` hop (the
  original client behind the nginx proxy), falling back to `X-Real-IP`,
  then to the peer address for direct (non-proxied) access

Login attempts live in the separate `login_audit` table; session end
(logout) is audited as action `logout` / entity `session`.

## Viewing

- Admin-only page `/audit` (perm `audit.view`) with action/entity filters.
- API: `GET /admin/audit?entity_type=...` (paginated).

## Conventions

- `log_action` **never raises** — auditing must not break a request.
- New mutating endpoints must call it; `details` should carry enough to
  reconstruct what changed (it is a JSON *string* in the API output).
