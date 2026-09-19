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
"""

__version__ = "1.2.0"
