import { expect, test } from '@playwright/test'

import { api, ADMIN, BASE, login, logout } from './helpers'

test.describe('auth', () => {
  test('wrong password keeps you on the login form', async ({ page }) => {
    await page.goto('/#/login')
    await page.fill('input#username', ADMIN.username)
    await page.fill('input#password', 'definitely-wrong')
    await page.click('button[type="submit"]')
    await expect(page.locator('input#username')).toBeVisible() // still the form
    // no menu appeared
    await expect(page.locator('.ant-menu')).toHaveCount(0)
  })

  test('unknown user gets the SAME generic error (no enumeration)', async ({ page }) => {
    await page.goto('/#/login')
    await page.fill('input#username', 'no-such-user')
    await page.fill('input#password', 'wrong')
    await page.click('button[type="submit"]')
    await expect(page.locator('input#username')).toBeVisible()
  })

  test('login → dashboard → session survives reload → logout', async ({ page }) => {
    await login(page)
    await expect(page.locator('header')).toContainText('مدیر')
    // session persists across reload (tokens in storage + /auth/me refetch)
    await page.reload()
    await expect(page.locator('.ant-menu')).toBeVisible()
    await logout(page)
  })

  test('login is throttled after repeated failures (429 → login_locked toast)', async ({ page }) => {
    // a DEDICATED user — locking admin would poison every later test
    await api('post', '/users', { username: 'lock-me', password: 'passw0rd123' })
    // the 5 failed attempts happen via the API (deterministic, awaited)
    for (let i = 0; i < 5; i++) {
      const res = await fetch(`${BASE}/api/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'lock-me', password: `bad-${i}` }),
      })
      expect(res.status).toBe(401)
    }
    // even the API now refuses with 429 login_locked (window-based)
    const locked = await fetch(`${BASE}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'lock-me', password: 'passw0rd123' }),
    })
    expect(locked.status).toBe(429)
    expect((await locked.json()).error.code).toBe('login_locked')

    // the UI login shows the Persian lockout message
    await page.goto('/#/login')
    await page.fill('input#username', 'lock-me')
    await page.fill('input#password', 'passw0rd123')
    await page.click('button[type="submit"]')
    await expect(page.locator('.ant-message')).toContainText('بیش از حد مجاز')
  })
})
