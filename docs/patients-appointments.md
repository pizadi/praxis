# Patients & appointments

## Patients

- CRUD at `/patients` with omnibox search (`q`): first/last name, national
  ID and phone number, all SQL-side `ILIKE`. Advanced filters: national-ID
  substring, phone substring, and multi-select tags/diagnoses (patients must
  have ALL selected).
- National ID is 10 digits, unique among live patients (partial unique
  index) — a deleted patient's ID is reusable.
- Deleting a patient is a soft delete: the whole subtree (appointments,
  files, payments, questionnaires) disappears from live views through join
  filtering and comes back on restore. See [trash-soft-delete.md](trash-soft-delete.md).

## Appointments

- Belong to a patient; `scheduled_at` is a timezone-aware datetime (the UI
  picks it with a Jalali picker, defaults to *now*).
- Medical notes — CC (`cm`), history (`hx`), exam (`px`), prescription
  (`rx`) — are visible/editable only with `medical_notes.view`
  (server-blanked otherwise).
- The patient page is a three-segment workspace (نوبت‌ها / همه فایل‌ها /
  پرسش‌نامه‌ها). Switching segments, switching appointments, leaving the
  page via the sidebar menu, or closing/refreshing the tab with unsaved
  changes warns: segment/appointment switches and menu navigation open a
  three-way confirmation (save & continue / discard / stay); tab close uses
  the browser's native «leave site?» dialog.
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
