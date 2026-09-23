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
  1.3.0.dev4  prescription update no longer violates the links unique
         constraint when item pairs are kept (flush orphan deletes first);
         prescription form rows: trailing empty row auto-appends on typing,
         abandoned empty rows removed on blur, Enter never submits
  1.3.0.dev5  prescription EDIT mode gets the trailing empty row too (new
         items were impossible to add when editing); taxonomies menu entry
         moved back to the management group
  1.3.0.dev6  appointment visit stages (reserved → checked-in → referred →
          finished) with ±1 advance/regress (regress confirmed, perm
          appointments.stage for front-desk check-in); audit trail records
          the real client IP behind the nginx proxy (X-Forwarded-For /
          X-Real-IP); the appointment panel shows the patient's same-day
          files, prescriptions and questionnaire responses («این روز»
          tabs, APP_TZ day of the appointment; all-history views live on
          the patient page); composite (patient_id, date) indexes on
          attachments / questionnaire_responses / prescriptions
  1.3.0.dev7  backup tarballs: optional AES-256-GCM encryption
          (BACKUP_ENCRYPTION_KEY — the artifact downloads as .enc, the
          importer decrypts it), SHA-256 of the whole artifact in the
          status + download header (optional expected_sha256 on import),
          and member-level checksums in the manifest (schema_version 4,
          verified member-by-member before the destructive import);
          stale-backup warning banner for admins (BACKUP_STALE_DAYS,
          default 7, 0 disables) driven by durable completion records in
          the audit trail
  1.3.0.dev8  test-suite rewrite: backend unit/api/parity split with
          shared factories + a permissions matrix sweep; frontend testing
          (vitest + Testing Library; Playwright E2E against a scratch
          stack); questionnaire-validator parity corpus
          (testdata/questionnaire_parity.json) run by BOTH pytest and
          vitest — pinned the TS formula length/depth limits and the
          server's whitespace-only-formula normalization; testdata
          contract keeps the error-message mapping in sync
  1.3.0  release
  1.3.1.dev1  backup download via the NATIVE browser download manager
          (POST download-token issues a short-lived HMAC token; GET
          download?token= accepts it — a plain navigation cannot send
          the Authorization header); the artifact is no longer fetched
          as an in-memory axios blob (on slow links nothing showed for
          the whole transfer). Artifacts persist in BACKUP_DIR (default
          <upload_dir>/.backups — hidden dir on the uploads volume:
          purge-safe, never archived into the next tarball) and are
          re-discovered at startup after a restart; a new backup
          atomically replaces the single artifact (the old per-run
          mkstemp leak fixed). Patient page: responsive columns (the
          sidebar/main split stacks below lg), the layout scroll
          container scrolls both axes, render errors are contained by
          an ErrorBoundary, and engines without :where() (Chrome/Edge
          < 88) get an upgrade banner instead of silently broken pages
  1.3.1.dev2  root /health alias for /api/v1/health (uptime monitors and
          manual checks hit the bare path on the host port — the 404
          looked like the API being down); prescription-item dictionary
          gains a manual create endpoint (POST /prescription-items,
          perm prescriptions.write, case-insensitive uniqueness) so the
          taxonomies page's «افزودن» works on all three lists
  1.3.1.dev3  production boot guard: CLINIC_ENV=production refuses to
          start without a PostgreSQL DATABASE_URL (a lost env var used
          to silently boot SQLite while looking healthy — real patient
          data written into a throwaway file); purge_db.py no longer
          hangs forever on DROP SCHEMA (lock_timeout + statement
          timeout — a running api container's connections were the
          blocker), warns about other connected backends up front, and
          fails loudly with a «docker compose stop api» hint
  1.3.1.dev4  purge_db.py --disconnect-others: terminate stray sessions
          on the target DB before the drop (a DB tool left idle in
          transaction blocks DROP SCHEMA even with the api stopped —
          bit once already); the guard fires only with the flag
  1.3.1.dev5  purge_db.py: NullPool + explicit connection scoping — the
          old engine.connect() left abandoned to the garbage collector
          lingered as an 'idle in transaction' session that our own
          --disconnect-others killed, and the pool's deferred reset
          logged 'server closed the connection unexpectedly' (harmless
          but alarming); verified: stray holder → 1 disconnect, no pool
          noise, purge completes
  1.3.1.dev6  backup import accepts huge tarballs: nginx drops the body
          cap for exactly POST /admin/backup/import (client_max_body_size
          0 + request buffering off — attachments keep their 50 MB cap);
          the upload spools onto the persistent volume (BACKUP_DIR, not
          container /tmp); the UI hashes the file incrementally (never
          whole-file in memory) and shows live hashing + upload progress
  1.3.1.dev7  import summary: the version-skew warning no longer shows
          when there is NO skew (an empty dict is truthy in JS — the
          warning rendered with empty parens); the PG import no longer
          sends a redundant BEGIN (psycopg2 already opens the
          transaction — silenced the server's 'there is already a
          transaction in progress' warning)
  1.3.1.dev8  after a purge the staleness check counts the persisted
          artifact (its mtime) alongside the audit completion rows —
          the site no longer banners 'never backed up' while the
          restorable tarball sits right there (the purge wipes the
          audit trail, not the volume)
  1.3.1  release
  1.4.0  UI overhaul: six VibeFarsi palettes (graphite/turquoise/saffron/
          pomegranate/lapis/paper) replace the light-dark toggle with a
          session-scoped switcher (sessionStorage, no-flash bootstrap);
          responsive layout — mobile drawer navigation, fluid tables/
          stacked rows on narrow viewports, fluid modals; taxonomies page
          renamed «موجودیت‌ها» and tabbed; prescription items get a direct
          creation endpoint; e2e mobile-viewport smoke project
  1.4.1.dev1  reconciliation merge: the 1.3.1 hardening line (backup
          download/import, purge_db, production boot guard, patient-page
          hardening) lands on top of the 1.4.0 UI overhaul; both branches
          had independently added the same POST /prescription-items
          endpoint — kept once with the richer 1.4.0 tests; the
          scroll-both-axes fix re-applies on the new layout
"""

__version__ = "1.4.1.dev1"
