/**
 * Appointment visit stages (1.4) — mirrors backend
 * app.models.domain.AppointmentStage (SmallInteger values on the wire).
 */

export interface VisitStage {
  value: number
  label: string
  /** antd Tag color */
  color: string
}

export const APPOINTMENT_STAGES: VisitStage[] = [
  { value: 0, label: 'رزرو شده', color: 'gold' },
  { value: 1, label: 'پذیرش شده', color: 'cyan' },
  { value: 2, label: 'ارجاع داده شده', color: 'purple' },
  { value: 3, label: 'پایان یافته', color: 'green' },
]

export const LAST_STAGE = APPOINTMENT_STAGES.length - 1

export function stageOf(value: number): VisitStage {
  return APPOINTMENT_STAGES[value] ?? APPOINTMENT_STAGES[0]
}

/**
 * The Asia/Tehran calendar day (YYYY-MM-DD) of an ISO timestamp — the
 * server interprets `date=` filters in APP_TIMEZONE, so the visit tabs
 * must query the same day, not the browser's local day.
 */
export function tehranDay(iso: string): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tehran' }).format(
    new Date(iso),
  )
}
