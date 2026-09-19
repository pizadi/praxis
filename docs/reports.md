# Stats & reports

## Dashboard (`/`)

- Landing page after login; today's appointments and quick counters.

## Daily schedule (`/schedule`)

- Day view of appointments with Jalali navigation; deep-links into the
  patient page (`/patients/{id}?appt={id}`).

## Today's payments (`/payments`, perm `payments.view`)

- Day-wide payments table + per-description summary — see
  [payments.md](payments.md).

## Stats (`/stats`, perm `stats.view`)

- Range queries over appointments/payments (Jalali date pickers; the API
  contract stays Gregorian ISO).
