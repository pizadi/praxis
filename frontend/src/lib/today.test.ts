import { afterEach, describe, expect, it, vi } from 'vitest'

import { localToday, serverToday } from './today'

// mock the api client module — serverToday must fall back to the LOCAL clock
// when the server is unreachable, and never use UTC's toISOString for "today"
vi.mock('../api/client', () => ({
  api: { get: vi.fn() },
}))

const { api } = await import('../api/client')
const mockedGet = vi.mocked(api.get)

afterEach(() => {
  vi.resetAllMocks()
})

describe('serverToday', () => {
  it('uses the server (APP_TZ) today', async () => {
    mockedGet.mockResolvedValueOnce({ data: { today: '2026-09-21' } })
    await expect(serverToday()).resolves.toBe('2026-09-21')
    expect(mockedGet).toHaveBeenCalledWith('/meta/today')
  })

  it('falls back to the local clock when the server is unreachable', async () => {
    mockedGet.mockRejectedValueOnce(new Error('down'))
    const result = await serverToday()
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(result).toBe(localToday())
  })
})

describe('localToday', () => {
  it('is a UTC calendar date (fallback only — Tehran days roll over at 20:30 UTC)', () => {
    expect(localToday()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})
