# Files (attachments)

## Data model

Two kinds of rows in `attachments`:

1. **Real files** — `stored_filename` set (UUID + sanitized extension under
   `UPLOAD_DIR`), plus `original_filename`, `mime_type`, `size_bytes`.
2. **Note-only rows** — `stored_filename IS NULL` **and**
   `original_filename IS NULL`; created via
   `POST /appointments/{id}/files/note` (doctor+).

`missing_file=True` means "a file was expected but is absent" (a migration
artifact) — NOT note-only.

## Endpoints

| Action | Endpoint | Perm |
| --- | --- | --- |
| List per appointment | `GET /appointments/{id}/files` | `files.read` |
| Upload (multipart, description/notes as form fields) | `POST /appointments/{id}/files` | `files.write` |
| Note-only row | `POST /appointments/{id}/files/note` | `files.write` |
| Edit description/notes | `PATCH /appointments/files/{id}` | `files.write` |
| **Attach/replace content** | `POST /appointments/files/{id}/content` | `files.write` |
| Download | `GET /appointments/files/{id}/download` | `files.read` |
| Soft delete | `DELETE /appointments/files/{id}` | `files.delete` |

- **Attach/replace content**: a note-only row gains a file, a `missing_file`
  row is repaired, an existing file is replaced — description/notes are
  preserved, `missing_file` clears, and the action is audited. The
  **superseded physical file stays on disk** (trash purge remains the only
  unlink path); replaced files become orphans that the automatic uploads
  purge reclaims after the grace period.
- The partial unique index `uq_attachments_stored_filename_live` tolerates
  multiple NULLs, so note-only rows never collide.
- Uploads are **streamed** to disk in chunks with the size cap
  (`MAX_UPLOAD_BYTES`, default 50 MB) enforced mid-read — an oversized
  upload is rejected (413) without ever buffering the whole body in memory,
  and no partial file is left behind.
- Read paths filter the whole parent chain: a file is visible only if
  itself + appointment + patient are alive.

## UI

- Patient page → «همه فایل‌ها»: sidebar list (row click selects — no
  expandable rows) + `FileDetailPane`: title, شرح, upload date (Jalali),
  size, editable notes (`FileNotesExpanded`), authorized download.
- **Preview**: images (zoom toolbar, in-page) and PDFs (browser viewer) are
  fetched as authorized blobs → object URLs (revoked on change/unmount, and
  refetched when `stored_filename` changes — the content-identity signal
  exposed by `AttachmentOut`).
- **Never render attachments from bare URLs** — the download endpoint needs
  the `Authorization` header; always go through `lib/files.ts::
  downloadAttachment` or an axios blob request.
- Uploads go through the axios client (`api.post` with `FormData`; antd
  `Upload` only selects the file via `beforeUpload: () => false`) — never
  antd's auto-XHR upload path, which bypasses the token-refresh interceptor.
