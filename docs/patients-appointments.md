# Patients & appointments

## Patients

- CRUD at `/patients` with omnibox search (`q`): first/last name via
  `ILIKE`, national ID and phone number via `like` (equivalent for their
  digits-only values). Advanced filters: first/last name, insurance,
  year of birth, gender, national-ID substring, phone substring, and
  multi-select tags/diagnoses (patients must have ALL selected).
- Patient form: users holding `taxonomies.write` can create a new
  tag/diagnosis inline — typing a name that matches nothing offers
  «افزودن «…»»; the entry is created (audited) right before the patient
  form is submitted. Other users see the existing list only.
- Tags/diagnoses are always alphabetical: production PostgreSQL sorts via
  an ICU `fa` collation on the `name` column (migration `f9e8d7c6b5a4` —
  `ORDER BY name` is index-backed, correct ا ب پ ت … order); dev SQLite
  falls back to binary order.
- **Merge on rename**: renaming «foo» to an existing «bar» returns 409
  `name_taken` and the UI offers a merge. Confirming (same
  `taxonomies.write` perm that gates tag/diag deletion) moves the patient
  links to «bar» (patients holding both keep one), soft-deletes «foo»
  (name reusable; trash can restore it pre-purge), all in one transaction,
  audited as action `merge`. API: `PATCH /tags/{id}?merge=true`.
- National ID is 10 digits, unique among live patients (partial unique
  index) — a deleted patient's ID is reusable.
- Deleting a patient is a soft delete: the whole subtree (appointments,
  files, payments, questionnaires) disappears from live views through join
  filtering and comes back on restore. See [trash-soft-delete.md](trash-soft-delete.md).

## Appointments

- Belong to a patient; `scheduled_at` is a timezone-aware datetime (the UI
  picks it with a Jalali picker, defaults to *now*).
- Medical notes — CC (`cm`), history (`hx`), exam (`px`), and the
  deprecated free-text prescription archive (`rx`) — are visible/editable
  only with `medical_notes.view` (server-blanked otherwise). Structured
  prescriptions replaced the rx text field in 1.3
  (see [prescriptions.md](prescriptions.md)); the rx column of old
  appointments is read-only («نسخه قدیمی» collapse).

### Visit stages

- Every appointment is in one of four stages, in a linear pipeline:
  رزرو شده (Reserved) → پذیرش شده (Checked-in) → ارجاع داده شده
  (Referred) → پایان یافته (Finished). Stored as a SmallInteger
  (`appointments.stage`, values 0–3, mirroring
  `app.models.domain.AppointmentStage`).
- `PATCH /appointments/{id}/stage` moves ONE step: `{"direction":
  "advance" | "regress"}`. The server computes the target and enforces the
  boundaries — moving past finished / before reserved is 409
  `stage_limit`. Perm: `appointments.stage` (admin/doctor/**receptionist**
  — check-in is a front-desk task; appointment *editing* stays
  `appointments.update`, doctor+). Every change is audited with the old/new
  stage in the details.
- UI: the appointment panel shows a stage tag with advance (one click) and
  regress buttons — regression asks for confirmation first. The schedule
  rows and the patient page's appointment list carry the tag + a
  quick-advance chip.
- Migration `d2e3f4a5b6c7` added the column and backfilled: appointments
  already in the past became پایان یافته; future ones stayed رزرو شده.

### Same-day visit tabs

- Files, prescriptions and questionnaire responses belong to the PATIENT
  (since 1.3). The opened appointment shows the **same-day** items of that
  patient in three extra tabs: فایل‌های این روز / نسخه‌های این روز /
  پرسش‌نامه‌های این روز (the all-history views stay on the patient page).
- "Same day" = the appointment's `scheduled_at` **calendar day in
  `APP_TZ`** — the three patient-level list endpoints accept a `date=`
  filter (each still gated by its own read permission, so a receptionist
  sees no prescriptions here either). The composite indexes
  `(patient_id, created_at/prescribed_at)` (migration `d2e3f4a5b6c7`)
  back the lookup.

- The patient page is a four-segment workspace (نوبت‌ها / همه فایل‌ها /
  پرسش‌نامه‌ها / نسخه‌ها). Switching segments, switching appointments,
  leaving the page via the sidebar menu, or closing/refreshing the tab
  with unsaved changes warns: segment/appointment switches and menu
  navigation open a three-way confirmation (save & continue / discard /
  stay); tab close uses the browser's native «leave site?» dialog.
- **Technical guard-rail**: `AppointmentPanel` must be mounted with
  `key={appointmentId}` — rc-field-form does not re-apply `initialValues`
  on re-render, and without the remount the previous appointment's notes
  stay in the form (and would overwrite the wrong appointment on save).

## Tags & diagnoses

- Taxonomy tables (`tags`, `diagnoses`) with M2M links to patients.
- `GET /tags` / `GET /diagnoses` support `q` (substring search) and
  `limit`/`offset` pagination (`Page`); the cap for these routers is 1000
  so the patient filter/create selects can fetch full lists.
- Soft delete keeps the M2M links so restoring is lossless.
