import { describe, expect, it } from 'vitest'

import { LAST_STAGE, APPOINTMENT_STAGES, stageOf, tehranDay } from './stages'

describe('stageOf', () => {
  it('maps the pipeline in order with Persian labels', () => {
    expect(APPOINTMENT_STAGES.map((s) => s.label)).toEqual([
      'رزرو شده',
      'پذیرش شده',
      'ارجاع داده شده',
      'پایان یافته',
    ])
    expect(stageOf(0).label).toBe('رزرو شده')
    expect(stageOf(3).label).toBe('پایان یافته')
  })

  it('falls back to reserved for unknown values', () => {
    expect(stageOf(99).value).toBe(0)
  })

  it('exposes the last stage for button disabling', () => {
    expect(LAST_STAGE).toBe(3)
  })
})

describe('tehranDay (the visit-tabs day logic — server interprets date= in APP_TZ)', () => {
  it('keeps the Tehran day inside the day', () => {
    expect(tehranDay('2026-09-21T10:00:00Z')).toBe('2026-09-21') // 13:30 Tehran
    expect(tehranDay('2026-09-21T15:59:00Z')).toBe('2026-09-21') // 19:29 Tehran
  })

  it('rolls over: ≥20:30 UTC is the NEXT Tehran day (the UTC≠Tehran trap)', () => {
    expect(tehranDay('2026-09-21T20:30:00Z')).toBe('2026-09-22') // 00:00 Tehran
    expect(tehranDay('2026-09-21T23:00:00Z')).toBe('2026-09-22') // 02:30 Tehran
  })

  it('handles the DST-less Tehran offset from winter dates too', () => {
    expect(tehranDay('2026-01-01T20:29:00Z')).toBe('2026-01-01') // 23:59 Tehran
    expect(tehranDay('2026-01-01T20:30:00Z')).toBe('2026-01-02') // 00:00 Tehran
  })
})
