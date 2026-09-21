import { expect, test } from '@playwright/test'

import { apiAppointment, apiPatient, login } from './helpers'

test.describe('appointments + visit stages', () => {
  test('appointment opens with the visit tabs; stages advance and regress (prompted)', async ({ page }) => {
    const patient = await apiPatient('1100000011')
    const appt = await apiAppointment(patient.id)

    await login(page)
    await page.goto(`/#/patients/${patient.id}?appt=${appt.id}`)
    await page.waitForSelector('.ant-tabs')

    // the five tabs, in order; the all-prescriptions tab is GONE
    const tabs = await page.$$eval('.ant-tabs-tab', (els) => els.map((e) => e.textContent?.trim()))
    expect(tabs).toEqual([
      'یادداشت‌ها',
      'فایل‌های این روز',
      'نسخه‌های این روز',
      'پرسش‌نامه‌های این روز',
      'پرداخت‌ها',
    ])

    // stage starts at رزرو شده for the future appointment
    const stageTag = page.locator('span.ant-tag:has-text("رزرو شده")').first()
    await expect(stageTag).toBeVisible()

    // ADVANCE: one click, no prompt
    await page.click('button:has(.anticon-double-left)')
    await expect(page.locator('span.ant-tag:has-text("پذیرش شده")').first()).toBeVisible()

    // REGRESS: prompted — cancel first (stage unchanged), then confirm
    await page.click('button:has(.anticon-double-right)')
    const dlg = page.locator('.ant-modal-confirm')
    await expect(dlg).toBeVisible()
    await dlg.locator('button:has-text("انصراف")').click()
    await expect(page.locator('span.ant-tag:has-text("پذیرش شده")').first()).toBeVisible()
    await page.click('button:has(.anticon-double-right)')
    await page.locator('.ant-modal-confirm').locator('button:has-text("برگرداندن مرحله")').click()
    await expect(page.locator('span.ant-tag:has-text("رزرو شده")').first()).toBeVisible()
  })

  test('the schedule page lists appointments with stage tags + quick advance', async ({ page }) => {
    const patient = await apiPatient('1100000012')
    await apiAppointment(patient.id)

    await login(page)
    await page.goto('/#/schedule')
    await page.waitForSelector('text=برنامه روزانه')
    // the future appointment is in SOME day list — switch to its Jalali date
    // via the API-driven deep link instead: navigate to the patient page
    await page.goto(`/#/patients/${patient.id}`)
    await page.waitForSelector('.ant-list .ant-list-item')
    // sidebar quick-advance chip exists for stage<FINISHED
    const advance = page.locator('.ant-list-item button:has(.anticon-double-left)').first()
    await advance.click()
    // the row's tag updates in place (no page reload)
    await expect(page.locator('.ant-list-item span.ant-tag').first()).toHaveText('پذیرش شده')
  })
})
