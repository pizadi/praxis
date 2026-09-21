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
"""

__version__ = "1.2.2"
