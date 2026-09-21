import { expect, test } from '@playwright/test'

import { apiAppointmentToday, apiPatient, login } from './helpers'

test.describe('files (patient-level)', () => {
  test('upload → appears in «فایل‌های این روز» with download', async ({ page }) => {
    const patient = await apiPatient('1500000051')

    await login(page)
    await page.goto(`/#/patients/${patient.id}`)
    await page.click('.ant-segmented-item:has-text("همه فایل‌ها")')
    await page.click('button:has-text("افزودن فایل")')

    const modal = page.locator('.ant-modal:visible')
    await modal.locator('input[type="file"]').setInputFiles({
      name: 'lab.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('e2e file content'),
    })
    await modal.locator('input[id$="description"], input#description, textarea').first().fill('آزمایش')
    await modal.locator('.ant-modal-footer .ant-btn-primary').click()
    await expect(page.locator('.ant-message')).toContainText(/ثبت|آپلود/)

    // the same-day tab on the appointment shows it (visit day = today)
    const appt = await apiAppointmentToday(patient.id)
    await page.goto(`/#/patients/${patient.id}?appt=${appt.id}`)
    await page.reload()
    await page.click('.ant-tabs-tab:has-text("فایل‌های این روز")')
    await expect(page.locator('.ant-tabs-tabpane-active')).toContainText('آزمایش')
    await expect(page.locator('.ant-tabs-tabpane-active button:has-text("دانلود")')).toBeVisible()
  })

  test('note-only row (no physical file) has no download button', async ({ page }) => {
    const patient = await apiPatient('1500000052')
    await login(page)
    await page.goto(`/#/patients/${patient.id}`)
    await page.click('.ant-segmented-item:has-text("همه فایل‌ها")')
    await page.click('button:has-text("افزودن فایل")')
    const modal = page.locator('.ant-modal:visible')
    await modal.locator('input[id$="description"], input#description, textarea').first().fill('یادداشت بدون فایل')
    await modal.locator('.ant-modal-footer .ant-btn-primary').click()
    await expect(page.locator('.ant-message')).toContainText(/ثبت|آپلود/)
    // the files table row selects it; the detail pane shows no download
    await page.locator('.ant-table-row', { hasText: 'یادداشت بدون فایل' }).click()
    await expect(page.locator('.ant-card:has-text("همه فایل‌ها") button:has-text("دانلود")')).toHaveCount(0)
  })
})
