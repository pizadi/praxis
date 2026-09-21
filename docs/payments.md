# Payments

## Model

- A transaction (`transactions`) belongs to an **appointment**; cash-vs-card
  is the `pos` boolean (نقدی / کارت‌خوان).
- `Transaction` has **no `created_at`** — the payment timestamp is the
  appointment's `scheduled_at`.

## Day-wide payments view

- `GET /payments?date=` — every payment of the day, day boundaries computed
  on the appointment's `scheduled_at` in `APP_TZ` (Asia/Tehran); defaults to
  today-in-Tehran. Receptionist+.
- `GET /payments/summary?date=` — per-description aggregates for the same
  day (`PaymentTypeStat`: count / total / POS / cash split).

## Gotchas

- Tests must derive «today» from `APP_TZ` — UTC and Tehran dates differ
  between ~20:30–00:00 UTC (this made payment tests fail at night before
  the fix; see `tests/api/test_payments.py::_today`).
- Legacy payment descriptions (`Visit`/`Spiro`/`Other`) are translated by
  the migration tooling to ویزیت/اسپیرو/سایر.
