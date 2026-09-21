"""Clinic management API.

Version history:
  1.0.0  legacy-rewrite baseline (patients/appointments/files/payments,
         roles & permissions, soft deletes/trash, audit, backup)
  1.1.0  questionnaire scoring formulas, cross-patient responses report
         (+ CSV export), file detail pane with preview/zoom and
         attach/replace file content, unsaved-changes guard, modal
         close-behavior hardening
  1.2.0  searchable/paginated taxonomies, categorized sidebar, backup
         import with tarball versioning + rollback, automatic uploads
         purge, route-level + tab-close unsaved-changes guard,
         documentation (docs/ + docs_fa/ + README_fa)
  1.2.1  security audit fixes: per-username login lockout (429
         login_locked), timing-equalized login, logout audited + called by
         the UI, refresh-token revocation on password change/deactivation,
         streamed uploads with mid-read size cap, partial-backup import
         fix, SQLite identifier escaping, CLINIC_ENV in compose, nginx
         headers, UTC-"today" fix (server /meta/today), dark-mode color
         tokens, Persian role display names, roles dialog preselects
         existing permissions
  1.2.2.dev1  patient form: inline creation of new tags/diagnoses for
         taxonomies.write holders (created at submit, before the patient
         save); questionnaire builder: hover plus button inserts a question
         at the start or between questions
  1.2.2.dev2  tags/diagnoses: Persian alphabetical order at the DB level
         (ICU fa_sort column collation, migration f9e8d7c6b5a4; patient
         tag/diagnosis lists ordered too); rename-onto-existing offers a
         merge (links move to the survivor, source soft-deleted, one
         transaction, audited as action merge)
  1.2.2  Persian-digit input normalization (DigitInput for national ID,
         birth year, phone, payment amount; questionnaire number inputs
         + patient search normalize Persian digits); range hints on
         questionnaire number questions
  1.3.0.dev1  files belong to the PATIENT (not the appointment); structured
         prescriptions (prescriptions / prescription_items / links with
         quantities, autocomplete, patient-level history) replacing the
         legacy free-text rx field; legacy rx → prescriptions data
         migration (frequency-based dictionary admission, verbatim
         overflow in notes, rx column kept as deprecated archive);
         backup manifest schema_version 3 + pre-1.3 attachment remap on
         import; legacy sqlite import script converts rx the same way
  1.3.0.dev2  the app migrates the database at startup (fail-fast, any
         launch path; create-all dev DBs stamped at head, fresh SQLite is
         create_all+stamp); legacy Django models.py/views.py removed;
         scripts/snapshot_db.py (pg_dump via docker exec / sqlite copy)
         and scripts/purge_db.py (full reset incl. users, snapshot-gated,
         admin re-bootstrapped, optional --uploads wipe)
  1.3.0.dev3  bootstrap keeps the UI-locked admin role at the full permission
         catalog (heals stamped/pre-1.3-seeded DBs); the UI refetches
         /auth/me on every load (cached-permission staleness); prescription
         items dictionary panel on the taxonomies page; unused JWT role
         claim removed; route-level code splitting (antd/vendor/dayjs
         chunks); stale artifacts removed, single nginx config source, MIT
         license
"""

__version__ = "1.3.0.dev3"
