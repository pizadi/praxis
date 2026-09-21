# Soft deletes & trash

## Semantics

- All deletions are **soft** (`deleted_at` timestamp) — domain tables,
  users, roles, questionnaire tables alike.
- Uniqueness (national ID, tag/diagnosis/user/role/template/prescription
  item names) is enforced only among live rows via **partial unique
  indexes** (`WHERE deleted_at IS NULL`), so a deleted value is reusable;
  restoring conflicts only when a live duplicate exists (409).
- Regular endpoints never hard-delete and never unlink physical files.
- Read paths filter `deleted_at IS NULL` across the whole parent chain — a
  file is visible only if itself + its patient are alive (patient-level
  since 1.3).

## Trash API (`app/api/v1/trash.py`)

| Action | Endpoint | Perm |
| --- | --- | --- |
| List deleted | `GET /admin/trash/{type}` | `trash.view` |
| Restore | `POST /admin/trash/{type}/{id}/restore` | `trash.restore` |
| Purge (permanent) | `DELETE /admin/trash/{type}/{id}` | `trash.purge` |

- **Subtree rule**: a child refuses restore (409 `parent_still_deleted`)
  while its parent is deleted; restoring the parent brings the subtree back.
- **Purge** is the only action that unlinks physical files — there is no
  undo.
- Covered types: patients, appointments, transactions, attachments, tags,
  diagnoses, users, roles, questionnaire_templates, questionnaire_responses,
  prescriptions, prescription_items.

## Related: the automatic uploads purge

Files on disk referenced by no attachment row (live or soft-deleted) are
swept automatically — see [backup-import.md](backup-import.md) →
"Uploads purge".
