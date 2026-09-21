import { expect, test } from '@playwright/test'

import { apiAppointment, apiPatient, apiTransaction, login } from './helpers'

test.describe('payments (day view)', () => {
  test("today's transactions appear with the pos/cash split", async ({ page }) => {
    const patient = await apiPatient('1600000061')
    const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tehran' }).format(new Date())
    const appt = await apiAppointment(patient.id, `${today}T09:00:00+03:30`)
    await apiTransaction(appt.id, 'ویزیت', 250000, true)
    await apiTransaction(appt.id, 'اسپیرو', 100000, false)

    await login(page)
    await page.goto('/#/payments')
    await page.waitForSelector('text=پرداخت‌های امروز')
    const listTable = page.locator('.ant-table', { hasText: 'بیمار' })
    await expect(listTable).toContainText('ویزیت')
    await expect(listTable).toContainText('کارت‌خوان')
    await expect(listTable).toContainText('نقدی')
    // the day total includes both amounts
    await expect(page.locator('text=۳۵۰,۰۰۰').first()).toBeVisible()
  })
})
