import { expect, test } from '@playwright/test'

import { apiAppointment, apiPatient, login } from './helpers'

/** The CC/HX/PX notes follow their own content: right for Persian, left for a
 * note that starts with a Latin letter. Regression: the fields used to be
 * locked to RTL, which mangled drug names and lab values pasted in. */
test.describe('note field direction', () => {
  test('CC/HX/PX align right for Persian, left for a Latin-first note', async ({ page }) => {
    const patient = await apiPatient('1200000031')
    const appt = await apiAppointment(patient.id)
    await login(page)
    await page.goto(`/#/patients/${patient.id}?appt=${appt.id}`)
    await page.waitForSelector('.ant-tabs')

    // the notes tab: «یادداشت» first, then CC / HX / PX
    const cc = page.locator('.ant-tabs-tabpane-active textarea').nth(1)
    await expect(cc).toHaveAttribute('dir', 'rtl')

    // typing a Persian note keeps it right-aligned
    await cc.fill('بیمار از درد قفسه سینه شکایت دارد')
    await expect(cc).toHaveAttribute('dir', 'rtl')
    await expect(cc).toHaveCSS('text-align', 'right')

    // an English note flips the whole field to left, live
    await cc.fill('Aspirin 100mg daily')
    await expect(cc).toHaveAttribute('dir', 'ltr')
    await expect(cc).toHaveCSS('text-align', 'left')

    // …and back again
    await cc.fill('سردرد خفیف')
    await expect(cc).toHaveAttribute('dir', 'rtl')

    // the other two clinical fields behave the same
    const hx = page.locator('.ant-tabs-tabpane-active textarea').nth(2)
    await hx.fill('WBC 12000')
    await expect(hx).toHaveAttribute('dir', 'ltr')
    await hx.fill('فشار خون بالا')
    await expect(hx).toHaveAttribute('dir', 'rtl')
  })

  test('an empty field starts right-aligned (the app default)', async ({ page }) => {
    const patient = await apiPatient('1200000032')
    const appt = await apiAppointment(patient.id)
    await login(page)
    await page.goto(`/#/patients/${patient.id}?appt=${appt.id}`)
    await page.waitForSelector('.ant-tabs')
    const px = page.locator('.ant-tabs-tabpane-active textarea').nth(3)
    await expect(px).toHaveAttribute('dir', 'rtl')
  })
})
