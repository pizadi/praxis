# Stats & reports

All day-based views take their initial date from the **server** (`GET
/meta/today` in `APP_TZ`), not the browser clock — the two disagree between
20:30–24:00 UTC (00:00–03:30 Tehran).

## Dashboard (`/`)

- Landing page after login; today's appointment count + today's appointment
  list.

## Daily schedule (`/schedule`)

- Day view of appointments with Jalali navigation; deep-links into the
  patient page (`/patients/{id}?appt={id}`).

## Today's payments (`/payments`, perm `payments.view`)

- Day-wide payments table + per-description summary — see
  [payments.md](payments.md).

## Stats (`/stats`, perm `stats.view`)

- Range queries over appointments/payments (Jalali date pickers; the API
  contract stays Gregorian ISO).
- `GET /stats/summary.csv` — server-side CSV export of the summary, with a
  button on the stats page.
