import { expect, test } from '@playwright/test'

import { api, apiAppointment, apiPatient, login } from './helpers'

const UNIQUE = Date.now().toString().slice(-8)

/** ASCII digits → Persian, mirroring the UI's FaNumber rendering. */
function toFa(s: string): string {
  const fa = '۰۱۲۳۴۵۶۷۸۹'
  return s.replace(/[0-9]/g, (d) => fa[Number(d)])
}

/** Fill the patient modal: the gender Select is the first .ant-select and is
 * REQUIRED — the form submits only once it carries a value. */
async function fillPatientModal(page: import('@playwright/test').Page, nationalId: string, firstName: string) {
  const modal = page.locator('.ant-modal:visible')
  await modal.locator('#national_id').fill(nationalId)
  await modal.locator('#first_name').fill(firstName)
  await modal.locator('#last_name').fill('مهربان')
  await modal.locator('#year_of_birth').fill('1370')
  await modal.locator('.ant-select').first().click()
  await page.locator('.ant-select-item:has-text("مرد")').click()
}

test.describe('patients', () => {
  test('create → lands on the new patient\'s page', async ({ page }) => {
    await login(page)
    await page.goto('/#/patients')
    await page.click('button:has-text("بیمار جدید")')
    await fillPatientModal(page, `09${UNIQUE}`, 'نیما')
    await page.locator('.ant-modal:visible .ant-modal-footer .ant-btn-primary').click()
    await expect(page.locator('.ant-message')).toContainText('ذخیره شد')

    // the create flow ends ON the new patient, not back on the list
    await page.waitForURL(/\/#\/patients\/\d+$/, { timeout: 10_000 })
    await expect(page.locator('.ant-card-head-title:has-text("نیما مهربان")')).toBeVisible()

    // ...and the record is findable from the list
    await page.goto('/#/patients')
    const search = page.getByPlaceholder('جستجو بر اساس نام، کد ملی یا شماره تلفن…')
    await search.fill(`09${UNIQUE}`)
    await search.press('Enter') // Input.Search fires onSearch on Enter, not on fill
    const row = page.locator('.ant-table-tbody tr.ant-table-row', { hasText: 'نیما مهربان' })
    await expect(row).toBeVisible({ timeout: 10_000 })
    // national IDs read as Persian digits — real, selectable text; the ASCII
    // clipboard form is pinned by the FaNumber unit tests (copy hook + button)
    await expect(row.locator('.fa-num').first()).toContainText('۰۹')
  })

  test('the list shows the insurance type', async ({ page }) => {
    const p = await apiPatient('1000000077', { insurance: 'بیمه تکمیلی' })
    await login(page)
    await page.goto('/#/patients')
    const search = page.getByPlaceholder('جستجو بر اساس نام، کد ملی یا شماره تلفن…')
    await search.fill(p.national_id)
    await search.press('Enter')
    // .ant-table-row skips antd's hidden measure row
    const row = page.locator('.ant-table-tbody tr.ant-table-row').first()
    await expect(row).toBeVisible({ timeout: 10_000 })
    await expect(row.locator('.fa-num').first()).toHaveText(toFa(p.national_id))
    await expect(row).toContainText('بیمه تکمیلی')
  })

  test('duplicate national id is refused (modal stays open with an error)', async ({ page }) => {
    await login(page)
    await page.goto('/#/patients')
    await page.click('button:has-text("بیمار جدید")')
    await fillPatientModal(page, `08${UNIQUE}`, 'اول')
    await page.locator('.ant-modal:visible .ant-modal-footer .ant-btn-primary').click()
    await expect(page.locator('.ant-message')).toContainText('ذخیره شد')
    await page.waitForURL(/\/#\/patients\/\d+$/, { timeout: 10_000 })

    // same ID again → refused (the modal STAYS open with an error, and we
    // stay on the list because nothing was created)
    await page.goto('/#/patients')
    await page.click('button:has-text("بیمار جدید")')
    await fillPatientModal(page, `08${UNIQUE}`, 'دوم')
    await page.locator('.ant-modal:visible .ant-modal-footer .ant-btn-primary').click()
    await expect(page.locator('.ant-modal:visible')).toBeVisible()
    await expect(page.locator('.ant-message')).toContainText(/National ID|موجود|تکراری/)
  })

  test('low viewport (1024×640): the four view lists render and are reachable', async ({ page }) => {
    // regression: on a smaller/older machine only the tab bar showed — the
    // lists below the fold never appeared (scroll container broke)
    const pid = (await apiPatient('1000000042')).id
    await apiAppointment(pid)
    await page.setViewportSize({ width: 1024, height: 640 })
    await login(page)
    await page.goto(`/#/patients/${pid}`)
    await expect(page.locator('.ant-segmented')).toBeVisible()

    // the SIDEBAR list card of each view: exact head title + contains a
    // list/table (the main pane card can carry the same title)
    const sidebarCard = (label: string) =>
      page
        .locator('.ant-card')
        .filter({ has: page.locator(`.ant-card-head-title:text-is("${label}")`) })
        .filter({ has: page.locator('.ant-list, .ant-table') })
        .first()

    const views = ['نوبت‌ها', 'همه فایل‌ها', 'پرسش‌نامه‌ها', 'نسخه‌ها']
    for (let i = 0; i < views.length; i++) {
      await page.locator('.ant-segmented .ant-segmented-item').nth(i).click()
      const card = sidebarCard(views[i])
      await expect(card).toBeVisible({ timeout: 10_000 })
      await card.scrollIntoViewIfNeeded()
      const box = await card.boundingBox()
      expect(box, `view card ${views[i]} must have a real box`).not.toBeNull()
      expect(box!.width).toBeGreaterThan(120)
      expect(box!.height).toBeGreaterThan(40)
    }
  })
})
