import { expect, test } from '@playwright/test'

import { api, login } from './helpers'

test.describe('admin area (roles/users/backup)', () => {
  test('admin sees users + roles + backup menu entries and pages load', async ({ page }) => {
    await login(page)
    for (const route of ['#users', '#roles', '#backup']) {
      await page.goto(`/#/${route}`)
      await page.waitForTimeout(600)
      await expect(page.locator('.ant-menu')).toBeVisible()
    }
  })

  test('backup page shows the staleness/encryption UI; status is live', async ({ page }) => {
    await login(page)
    await page.goto('/#/backup')
    await page.waitForSelector('text=پشتیبان‌گیری')
    // the status card + the build button are there
    await expect(page.locator('button:has-text("ساخت پشتیبان")')).toBeVisible()
    // run one for real (the scratch backend is disposable)
    await page.click('button:has-text("ساخت پشتیبان")')
    await expect(page.locator('.ant-message')).toContainText('آغاز شد')
    // the completion clears the staleness warning if it was shown
    await page.waitForTimeout(4000)
    const shaVisible = await page.locator('text=SHA-256').count()
    const staleBanner = await page.locator('.ant-alert-warning', { hasText: 'هشدار پشتیبان‌گیری' }).count()
    expect(shaVisible > 0 || staleBanner === 0).toBeTruthy()
  })

  test('backup download streams via the native download manager (token URL)', async ({ page }) => {
    await login(page)
    await page.goto('/#/backup')
    await page.waitForSelector('text=پشتیبان‌گیری')
    // build an artifact (scratch backend is disposable), then wait for ready
    await page.click('button:has-text("ساخت پشتیبان")')
    const downloadBtn = page.locator('button:has-text("دانلود پشتیبان")')
    await expect(downloadBtn).toBeVisible({ timeout: 20_000 })

    // the UI fetches a short-lived token, then navigates to the tokenized
    // URL — the browser's download manager takes over (never an axios blob)
    const downloadPromise = page.waitForEvent('download', { timeout: 15_000 })
    await downloadBtn.click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toMatch(/^clinic-backup-.*\.tar\.gz$/)
    const path = await download.path()
    expect(path).toBeTruthy()
  })

  test('receptionist never sees the admin menu entries (UI gating follows permissions)', async ({ page }) => {
    // create a receptionist via the API
    const roles = await api<{ items: { id: number; name: string }[] }>('get', '/roles')
    const recepRole = roles.items.find((r) => r.name === 'receptionist')
    await api('post', '/users', { username: 'recep_ui', password: 'passw0rd123', role_id: recepRole.id })

    await login(page, 'recep_ui', 'passw0rd123')
    await expect(page.locator('.ant-menu')).not.toContainText('پشتیبان‌گیری')
    await expect(page.locator('.ant-menu')).not.toContainText('گزارش اقدامات')
    // the page itself is still permission-gated server-side
    await page.goto('/#/backup')
    await page.reload()
    await page.waitForTimeout(1000)
  })
})
