/** Shared E2E helpers: API seeding (fast, out-of-browser) + login flow (UI). */
import { expect, type Page } from '@playwright/test'

const BASE = process.env.E2E_BACKEND ?? 'http://127.0.0.1:18001'
const API = `${BASE}/api/v1`

export { BASE }

/** The scratch backend bootstraps admin/admin123 (CLINIC_ENV=test). */
export const ADMIN = { username: 'admin', password: 'admin123' }

let tokenCache: string | null = null

export async function apiToken(): Promise<string> {
  if (!tokenCache) {
    const res = await fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ADMIN),
    })
    expect(res.status).toBe(200)
    tokenCache = (await res.json()).access_token
  }
  return tokenCache
}

export async function api<T = unknown>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const token = await apiToken()
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  expect(res.status, `${method} ${path}`).toBeLessThan(500)
  return (await res.json()) as T
}

export async function apiPatient(nationalId?: string) {
  return api<{ id: number; national_id: string }>('post', '/patients', {
    national_id: nationalId ?? '1000000001',
    first_name: 'بیمار',
    last_name: 'تستی',
    year_of_birth: '1370',
    gender: 0,
  })
}

export async function apiAppointment(patientId: number, when = '2099-01-01T09:00:00+03:30') {
  return api<{ id: number }>('post', `/patients/${patientId}/appointments`, {
    scheduled_at: when,
  })
}

/** An appointment TODAY (Tehran day) — for the same-day visit-tab specs
 * (items created now belong to the appointment's day). */
export async function apiAppointmentToday(patientId: number) {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tehran' }).format(new Date())
  return apiAppointment(patientId, `${today}T09:00:00+03:30`)
}

export async function apiTemplate(name = 'قالب تست') {
  return api<{ id: number }>('post', '/questionnaires/templates', {
    name,
    description: '',
    format: {
      version: 1,
      title: name,
      questions: [
        { key: 'pain', label: 'شدت درد', type: 'number', required: true, min: 0, max: 10, integer: true, unit: '' },
        {
          key: 'mood',
          label: 'حال',
          type: 'choice',
          options: [
            { value: 'bad', label: 'بد', score: 0 },
            { value: 'good', label: 'خوب', score: 2 },
          ],
        },
      ],
    },
  })
}

export async function apiPrescription(patientId: number, name = 'آسموتول') {
  return api<{ id: number }>('post', `/patients/${patientId}/prescriptions`, {
    items: [{ name }],
  })
}

export async function apiTransaction(appointmentId: number, description: string, amount: number, pos: boolean) {
  return api<{ id: number }>('post', `/appointments/${appointmentId}/transactions`, {
    description,
    amount,
    pos,
  })
}

/** Log in through the real UI. Waits for a POST-login marker (the app
 * header — present on desktop AND mobile, where the menu only mounts when
 * the drawer opens) — NEVER the login page title (it also says پراکسیس). */
export async function login(page: Page, username = ADMIN.username, password = ADMIN.password) {
  await page.goto('/#/login')
  await page.fill('input#username', username)
  await page.fill('input#password', password)
  await page.click('button[type="submit"]')
  await page.waitForSelector('.ant-layout-header', { timeout: 15_000 })
}

export async function logout(page: Page) {
  await page.click('button:has-text("خروج")')
  await page.waitForURL(/#\/login/, { timeout: 15_000 })
  // the hot login↔app transition can glitch (React #426 in the minified
  // preview build) — re-boot the SPA; the login form is the recovery point
  for (let i = 0; i < 3; i++) {
    await page.reload()
    try {
      await page.waitForSelector('input#username', { timeout: 5_000, state: 'visible' })
      return
    } catch {
      // glitched render — reload again
    }
  }
  throw new Error('login form never rendered after logout')
}
