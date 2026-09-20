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
  1.3.0  files belong to the PATIENT (not the appointment); structured
         prescriptions (prescriptions / prescription_items / links with
         quantities, autocomplete, patient-level history) replacing the
         legacy free-text rx field; legacy rx → prescriptions data
         migration (frequency-based dictionary admission, verbatim
         overflow in notes, rx column kept as deprecated archive);
         backup manifest schema_version 3 + pre-1.3 attachment remap on
         import; legacy sqlite import script converts rx the same way
"""

__version__ = "1.3.0"
