import { expect, test } from '@playwright/test'

import { login } from './helpers'

test.describe('questionnaire builder (admin)', () => {
  test('formula live check: unknown key flagged, valid formula accepted', async ({ page }) => {
    await login(page)
    await page.goto('/#/questionnaires')
    await page.click('button:has-text("قالب جدید")')

    // the builder modal opens EMPTY: add a number question first
    const modal = page.locator('.ant-modal:has-text("قالب جدید")')
    await expect(modal).toBeVisible()
    await modal.locator('button:has-text("پرسش جدید")').click()
    const keyInput = modal.locator('input[id*="key"]').first()
    await keyInput.fill('pain')
    // switch its type to number (the type select defaults to string)
    const typeSelect = modal.locator('.ant-select').first()
    await typeSelect.click()
    await page.locator('.ant-select-item:has-text("عدد")').first().click()
    await page.waitForTimeout(300)

    // unknown key → the SERVER-AUTHORITATIVE live check errors (debounced)
    const formula = modal.locator('#score_formula')
    await formula.fill('nope + 1')
    await expect(modal.locator('.ant-form-item-explain-error')).toContainText(/ناشناس/)

    // a valid formula over the question keys clears the error
    await formula.fill('pain * 2')
    await page.waitForTimeout(500)
    await expect(modal.locator('.ant-form-item-explain-error')).toHaveCount(0)
  })
})
