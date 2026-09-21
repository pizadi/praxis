import { expect, test } from '@playwright/test'

import { apiAppointment, apiPatient, login } from './helpers'

test.describe('prescriptions (same-day tab)', () => {
  test('quick-add registers the item and it appears in «نسخه‌های این روز»', async ({ page }) => {
    const patient = await apiPatient('1400000041')
    const appt = await apiAppointment(patient.id)

    await login(page)
    await page.goto(`/#/patients/${patient.id}?appt=${appt.id}`)
    await page.click('.ant-tabs-tab:has-text("نسخه‌های این روز")')

    await page.click('button:has-text("ثبت نسخه برای این بیمار")')
    const modal = page.locator('.ant-modal:visible')
    await expect(modal).toBeVisible()
    // mask-closable=false: clicking the backdrop must NOT close it
    await page.mouse.click(30, 300)
    await expect(modal).toBeVisible()

    // type an item name into the prescription item row (AutoComplete)
    // antd AutoComplete renders its placeholder as a span — target the
    // combobox input, not the placeholder
    const row = modal.getByRole('combobox').first()
    await row.fill('آسموتول 250')
    // close any open Jalali picker popup (its inputs cover the footer)
    await modal.locator('.ant-modal-header').click()
    await modal.locator('button:has-text("ثبت"), button[type="submit"]').first().click()

    // modal closes, the same-day list shows the prescription
    await expect(page.locator('.ant-message')).toContainText('نسخه ثبت شد')
    await expect(page.locator('.ant-tabs-tabpane-active')).toContainText('آسموتول 250')
  })

  test('a prescription from ANOTHER day does not appear in the same-day tab', async ({ page }) => {
    const patient = await apiPatient('1400000042')
    const appt = await apiAppointment(patient.id)
    // old prescription (different day) via the API
    await import('./helpers').then(({ api }) =>
      api('post', `/patients/${patient.id}/prescriptions`, {
        items: [{ name: 'دارای قدیمی' }],
        prescribed_at: '2020-01-01T10:00:00+03:30',
      }),
    )

    await login(page)
    await page.goto(`/#/patients/${patient.id}?appt=${appt.id}`)
    await page.click('.ant-tabs-tab:has-text("نسخه‌های این روز")')
    await expect(page.locator('.ant-tabs-tabpane-active')).toContainText('در این روز نسخه‌ای ثبت نشده است')
  })
})
