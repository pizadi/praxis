import { api } from '../api/client'

/** The browser clock's UTC calendar date — may disagree with Tehran between
 * 20:30–24:00 UTC (00:00–03:30 Asia/Tehran). Used only as a fallback. */
export function localToday(): string {
  return new Date().toISOString().slice(0, 10)
}

/** Server 'today' (APP_TIMEZONE) — the authoritative date for Jalali day
 * defaults (dashboard, schedule, payments). Falls back to the local clock
 * if the server is unreachable. */
export async function serverToday(): Promise<string> {
  try {
    return (await api.get<{ today: string }>('/meta/today')).data.today
  } catch {
    return localToday()
  }
}
