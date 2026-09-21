# Prescriptions (v1.3)

Structured replacement for the legacy free-text `appointments.rx` field.

## Data model

- `prescriptions` — belongs to a **PATIENT** (like questionnaire
  responses); `prescribed_at` timestamp, `notes`, `created_by_id` (user),
  soft delete. `source_appointment_id` records the appointment a
  prescription was migrated FROM (provenance only — no FK).
- `prescription_items` — tag-like dictionary (a drug, a test, an
  instruction); live names unique (partial index); soft delete; powers the
  autocomplete.
- `prescription_item_links` — (prescription, item) + `quantity`
  (NULL = unspecified/legacy). Unique pair per prescription; editing a
  prescription replaces its links.

## Legacy rx conversion (frozen rules — `app/services/rx_migration.py`)

The 1.3 migration (and `scripts/migrate_sqlite.py` for fresh imports)
converted every appointment's rx free text into one prescription:

- items split on commas/newlines; Persian digits normalized;
- a trailing standalone integer becomes the item's quantity (`P1 20` →
  P1 × 20; `MTX 15` → MTX × 15 — dose/count ambiguity accepted by design);
- names deduplicate on a normalized key (casefold, whitespace collapse,
  edge punctuation); the most frequent spelling is the display name;
- only names seen **≥ 3 times across the whole corpus** became dictionary
  items (~800 items from the legacy data, covering ~85% of occurrences);
  everything rarer (one-off sentences like "i should see ct for bx…",
  misspellings) is preserved **verbatim in the prescription's notes**;
- the original text also stays in the deprecated `appointments.rx` column
  (never written by the app anymore; still blanked server-side without
  `medical_notes.view`; shown read-only behind «نسخه قدیمی» in the UI).

These rules are **frozen** — both the Alembic migration and the legacy
import script share the same parser, and the unit tests pin them down.
Changing them would rewrite history differently on different installs.

## Endpoints

| Action | Endpoint | Perm |
| --- | --- | --- |
| Autocomplete dictionary search | `GET /prescription-items?q=` | `prescriptions.read` |
| Rename dictionary item (fix typos) | `PATCH /prescription-items/{id}` | `prescriptions.write` |
| Soft-delete dictionary item | `DELETE /prescription-items/{id}` | `prescriptions.write` |
| List patient prescriptions | `GET /patients/{id}/prescriptions` | `prescriptions.read` |
| Create | `POST /patients/{id}/prescriptions` | `prescriptions.write` |
| Get one | `GET /prescriptions/{id}` | `prescriptions.read` |
| Update (replaces items when given) | `PATCH /prescriptions/{id}` | `prescriptions.write` |
| Soft delete | `DELETE /prescriptions/{id}` | `prescriptions.write` |

- Creating/updating with an unknown item **name** auto-registers it in the
  dictionary (case-insensitive match first) — no separate taxonomy perm;
  prescribing doctors grow the vocabulary.
- Every write is audited; prescriptions are restorable from the trash
  (parent = patient).

## Permissions

`prescriptions.read` / `prescriptions.write` (new group «نسخ‌ها» in the
roles UI). Defaults: doctor = read+write, receptionist = none (prescriptions
are medical data, consistent with `medical_notes.view`), admin = all. The
1.3 migration adds the two permissions to the existing admin/doctor roles
additively (never removes anything).

## UI

- Patient page → «نسخه‌ها» (4th sidebar view): list + view/edit/create;
  items are chips (`name × qty`).
- Appointment panel → «نسخه‌ها» tab: the patient's prescriptions with a
  quick-add modal pre-dated to the visit's time; the legacy free-text rx of
  old appointments shows read-only in the notes tab («نسخه قدیمی» collapse).
- The editor: type an item name → suggestions from the dictionary
  (server search, debounced); a new name is auto-registered on save.
  Quantity input does NOT clamp (validation rule with a Persian message
  instead — the antd min/precision clamp bug pattern).
