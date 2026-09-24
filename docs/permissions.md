# Roles & permissions

Access control is **permission-based** — there is no role hierarchy in code.

## How it works

- Every endpoint calls `require_perm("...")` (any-of semantics) from
  `app/api/deps.py`.
- Each role row holds a permission set (JSON array of catalog keys); catalog
  keys and system-role sets live in `backend/app/core/permissions.py`
  (mirrored in migration `d4e5f6a7b8c9`). Persian labels live separately in
  `permission_labels_fa.py`, keeping UI copy out of authorization logic.
- Permissions are read from the DB **per request** (`selectinload(User.role)`
  is mandatory whenever a user is loaded) — permission changes apply
  immediately, without re-login.

## System roles (seeded idempotently by `bootstrap_admin()`)

| Role | Position |
| --- | --- |
| `admin` | all permissions; the role is **locked** (no edit/delete — lockout protection) |
| `doctor` | editable, not deletable |
| `receptionist` | editable, not deletable |

- Admins create **custom roles** at `/roles` (grouped permission
  checkboxes) and assign them at `/users`.
- A role in use refuses deletion (409).
- The UI hides actions via `hasPerm()` from `useUser()` — but the server is
  authoritative; hiding is cosmetic.

## Notable server-side gates

- `medical_notes.view` — the CM/HX/PX/RX fields of an appointment are
  **blanked server-side** for users without it (not just hidden in the UI).
- `appointments.stage` — advancing/regressing the visit pipeline
  (رزرو شده → پذیرش شده → ارجاع داده شده → پایان یافته; one step per call,
  audited). Granted to receptionists too — check-in is a front-desk task —
  while appointment *editing* stays `appointments.update` (doctor+).
- `prescriptions.read`/`prescriptions.write` — structured prescriptions
  (v1.3); doctor+ by default, receptionist none (see docs/prescriptions.md).
- `users.manage` ≡ admin; `roles.manage`, `audit.view`, `backup.manage`,
  `trash.purge` are the other admin-only abilities.
- `trash.view`/`trash.restore` — doctor+; `trash.purge` — admin only.
