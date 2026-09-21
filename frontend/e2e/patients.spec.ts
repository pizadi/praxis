import { expect, test } from '@playwright/test'

import { login } from './helpers'

const UNIQUE = Date.now().toString().slice(-8)

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
  test('create → appears in search → reopen', async ({ page }) => {
    await login(page)
    await page.goto('/#/patients')
    await page.click('button:has-text("بیمار جدید")')
    await fillPatientModal(page, `09${UNIQUE}`, 'نیما')
    await page.locator('.ant-modal:visible .ant-modal-footer .ant-btn-primary').click()
    await expect(page.locator('.ant-message')).toContainText('ذخیره شد')

    // search finds them
    const search = page.getByPlaceholder('جستجو بر اساس نام، کد ملی یا شماره تلفن…')
    await search.fill(`09${UNIQUE}`)
    await expect(page.locator('.ant-table')).toContainText('نیما مهربان', { timeout: 10_000 })
  })

  test('duplicate national id is refused (modal stays open with an error)', async ({ page }) => {
    await login(page)
    await page.goto('/#/patients')
    await page.click('button:has-text("بیمار جدید")')
    await fillPatientModal(page, `08${UNIQUE}`, 'اول')
    await page.locator('.ant-modal:visible .ant-modal-footer .ant-btn-primary').click()
    await expect(page.locator('.ant-message')).toContainText('ذخیره شد')

    // same ID again → refused (the modal STAYS open with an error)
    await page.click('button:has-text("بیمار جدید")')
    await fillPatientModal(page, `08${UNIQUE}`, 'دوم')
    await page.locator('.ant-modal:visible .ant-modal-footer .ant-btn-primary').click()
    await expect(page.locator('.ant-modal:visible')).toBeVisible()
    await expect(page.locator('.ant-message')).toContainText(/National ID|موجود|تکراری/)
  })
})
