import { expect, test } from '@playwright/test'

import { api, apiAppointmentToday, apiPatient, apiPrescription, apiTemplate, login } from './helpers'

test.describe('same-day visit tabs (files / prescriptions / questionnaires of the day)', () => {
  test('same-day items appear; other-day items do not', async ({ page }) => {
    const patient = await apiPatient('1700000071')
    const template = await apiTemplate('قالب ویزیت روز')
    const appt = await apiAppointmentToday(patient.id)

    // same-day items (created now = today): note-only file + a response
    await api('post', `/patients/${patient.id}/files/note`, { description: 'یادداشت روز' })
    await api('post', `/patients/${patient.id}/questionnaires`, {
      template_id: template.id,
      answers: { pain: 5, mood: 'good' },
    })

    // other-day item
    await api('post', `/patients/${patient.id}/prescriptions`, {
      items: [{ name: 'دارای قدیمی' }],
      prescribed_at: '2020-05-05T10:00:00+03:30',
    })

    await login(page)
    await page.goto(`/#/patients/${patient.id}?appt=${appt.id}`)

    // FILES tab: same-day note-only visible
    await page.click('.ant-tabs-tab:has-text("فایل‌های این روز")')
    await expect(page.locator('.ant-tabs-tabpane-active')).toContainText('یادداشت روز')

    // QUESTIONNAIRES tab: same-day response visible with its template name
    await page.click('.ant-tabs-tab:has-text("پرسش‌نامه‌های این روز")')
    await expect(page.locator('.ant-tabs-tabpane-active')).toContainText('قالب ویزیت روز')
  })

  test('a prescription from the visit day shows up in «نسخه‌های این روز»', async ({ page }) => {
    const patient = await apiPatient('1700000072')
    const appt = await apiAppointmentToday(patient.id)
    await apiPrescription(patient.id, 'دارای امروز')

    await login(page)
    await page.goto(`/#/patients/${patient.id}?appt=${appt.id}`)
    await page.click('.ant-tabs-tab:has-text("نسخه‌های این روز")')
    await expect(page.locator('.ant-tabs-tabpane-active')).toContainText('دارای امروز')
  })
})
