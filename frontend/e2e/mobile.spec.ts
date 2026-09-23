/**
 * Mobile-viewport smoke (390×844 — runs ONLY in the chromium-mobile project;
 * the desktop project ignores this file via testIgnore):
 *   - the 200px sidebar is replaced by a hamburger + right-side Drawer
 *   - the drawer navigates with the same grouped menu and closes on select
 *   - the theme switcher applies a palette session-scoped (survives reload)
 */
import { expect, test } from '@playwright/test'

import { apiPatient, login } from './helpers'

test.skip(({ viewport }) => (viewport?.width ?? 1280) >= 768, 'mobile-only spec')

test('mobile shell: drawer navigation and session-scoped theme', async ({ page }) => {
  await apiPatient()
  await login(page)

  // desktop sider must be gone; the hamburger must be there
  await expect(page.locator('.ant-layout-sider')).toHaveCount(0)
  const burger = page.getByRole('button', { name: 'منو' })
  await expect(burger).toBeVisible()

  // open the drawer, navigate through it
  await burger.click()
  const drawer = page.locator('.ant-drawer')
  await expect(drawer).toBeVisible()
  await drawer.locator('.ant-menu').waitFor()
  await drawer.locator('.ant-menu-item', { hasText: 'بیماران' }).click()
  // the drawer closes (its content unmounts); the fixed-inset wrapper stays
  // in the DOM with pointer-events:none, so assert on the content panel
  await expect(page.locator('.ant-drawer-content')).toBeHidden()
  await expect(page).toHaveURL(/#\/patients/)
  // the patients page renders its search input below md
  await expect(page.locator('input[placeholder*="جستجو"]')).toBeVisible()

  // theme switcher: کاغذ is the light palette → html.dark must drop
  await page.getByRole('button', { name: 'تم' }).click()
  await page.getByRole('menuitem', { name: /کاغذ/ }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'paper')
  expect(await page.locator('html').evaluate((el) => el.classList.contains('dark'))).toBe(false)

  // session-scoped: the choice survives a reload in this tab
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'paper')
})
