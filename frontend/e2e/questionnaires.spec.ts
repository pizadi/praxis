import { expect, test } from '@playwright/test'

import { apiPatient, apiTemplate, login } from './helpers'

test.describe('questionnaire fill', () => {
  test('valid submission saves; out-of-range shows the Persian inline error', async ({ page }) => {
    const patient = await apiPatient('1300000031')
    const template = await apiTemplate()

    await login(page)
    await page.goto(`/#/patients/${patient.id}`)
    // switch to the questionnaires view
    await page.click('.ant-segmented-item:has-text("پرسش‌نامه‌ها")')
    await page.click('text=پرسش‌نامه جدید')
    // pick the template
    const picker = page.locator('.ant-select:has-text("قالب پرسش‌نامه"), .ant-select').first()
    await picker.click()
    await page.locator('.ant-select-item:has-text("قالب تست")').first().click()
    await page.waitForTimeout(500)

    // out-of-range: the rule (NOT InputNumber clamping) must complain
    const spin = page.getByRole('spinbutton')
    await spin.fill('11')
    await page.click('button:has-text("ذخیره")')
    await expect(page.locator('.ant-form-item-explain-error', { hasText: 'بیشتر از حداکثر (10)' })).toBeVisible()

    // fix it and submit — the choice radio + required number are accepted
    await spin.fill('7')
    await page.getByRole('radio', { name: 'خوب' }).click()
    await page.click('button:has-text("ذخیره")')
    await expect(page.locator('.ant-message')).toContainText('پاسخ پرسش‌نامه ثبت شد')
  })

  test('an out-of-range answer via the API surfaces the SERVER field error inline (422 mapping)', async ({ page }) => {
    const patient = await apiPatient('1300000032')
    const template = await apiTemplate('قالب خطا')
    // fill the form with a value the SERVER rejects (the local rule passes —
    // integer boundary), then patch answers directly is out of scope here;
    // instead: submit 10.5 — InputNumber step may allow decimals
    await login(page)
    await page.goto(`/#/patients/${patient.id}`)
    await page.click('.ant-segmented-item:has-text("پرسش‌نامه‌ها")')
    await page.click('text=پرسش‌نامه جدید')
    const picker = page.locator('.ant-select').first()
    await picker.click()
    await page.locator('.ant-select-item:has-text("قالب خطا")').first().click()
    await page.waitForTimeout(500)
    const spin = page.getByRole('spinbutton')
    await spin.fill('10.5')
    await page.click('button:has-text("ذخیره")')
    await expect(page.locator('.ant-form-item-explain-error', { hasText: 'باید عدد صحیح باشد' })).toBeVisible()
    void template
  })
})
