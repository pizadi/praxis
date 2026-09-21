import { expect, test } from '@playwright/test'

import { apiAppointment, apiPatient, login } from './helpers'

test.describe('unsaved-changes guards', () => {
  test('dirty notes form → view switch asks: save / discard / stay', async ({ page }) => {
    const patient = await apiPatient('1200000021')
    const appt = await apiAppointment(patient.id)

    await login(page)
    await page.goto(`/#/patients/${patient.id}?appt=${appt.id}`)
    await page.waitForSelector('.ant-tabs')

    // dirty the notes form
    const notesArea = page.locator('.ant-tabs-tabpane-active textarea').first()
    await notesArea.fill('تغییر ذخیره‌نشده')

    // switching views via the Segmented must NOT navigate silently —
    // the 3-button dialog appears
    await page.click('.ant-segmented-item:has-text("همه فایل‌ها")')
    const dlg = page.locator('.ant-modal:has-text("تغییرات ذخیره نشده")')
    await expect(dlg).toBeVisible()
    await expect(dlg).toContainText('ذخیره و ادامه')

    // بازگشت → stays on the form, still dirty
    await dlg.locator('button:has-text("بازگشت به ویرایش")').click()
    await expect(page.locator('.ant-tabs')).toBeVisible()
    await expect(notesArea).toHaveValue('تغییر ذخیره‌نشده')

    // دورریختن تغییرات → the navigation completes, the change is dropped
    await page.click('.ant-segmented-item:has-text("همه فایل‌ها")')
    await page.locator('.ant-modal:has-text("تغییرات ذخیره نشده")').locator('button:has-text("دورریختن تغییرات")').click()
    await expect(page.locator('.ant-card-head-title:has-text("همه فایل‌ها")')).toBeVisible()
  })

  test('clean form → view switch navigates immediately (no dialog)', async ({ page }) => {
    const patient = await apiPatient('1200000022')
    const appt = await apiAppointment(patient.id)
    await login(page)
    await page.goto(`/#/patients/${patient.id}?appt=${appt.id}`)
    await page.waitForSelector('.ant-tabs')
    await page.click('.ant-segmented-item:has-text("همه فایل‌ها")')
    await expect(page.locator('.ant-modal:has-text("تغییرات ذخیره نشده")')).toHaveCount(0)
    await expect(page.locator('text=افزودن فایل').first()).toBeVisible()
  })
})
