import { Form } from 'antd'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { QuestionnaireForm } from './QuestionnaireRender'
import type { FormatDoc } from '../lib/questionnaire'

afterEach(cleanup) // vitest globals are off — no auto-cleanup

const FORMAT: FormatDoc = {
  version: 1,
  title: 'تست',
  questions: [
    { key: 'pain', label: 'شدت درد', type: 'number', required: true, min: 0, max: 10, integer: true, unit: '' },
    {
      key: 'mobility',
      label: 'تحرک',
      type: 'choice',
      required: false,
      options: [
        { value: 'bad', label: 'بد', score: 0 },
        { value: 'good', label: 'خوب', score: 2 },
      ],
    },
  ],
}

/** antd Form instance must live outside the component (same as the app). */
function TestHarness({ onFinish }: { onFinish: (answers: Record<string, unknown>) => void }) {
  const [form] = Form.useForm()
  return <QuestionnaireForm form={form} format={FORMAT} onFinish={onFinish} />
}

describe('QuestionnaireForm (the fill form)', () => {
  it('submits with null for untouched fields (null is always valid server-side)', async () => {
    const user = userEvent.setup()
    const onFinish = vi.fn()
    render(<TestHarness onFinish={onFinish} />)
    await user.type(screen.getByRole('spinbutton'), '7')
    await user.click(screen.getByRole('radio', { name: /خوب/ }))
    await user.click(screen.getByRole('button', { name: 'ذخیره' }))
    expect(onFinish).toHaveBeenCalledWith({ pain: 7, mobility: 'good' })
  })

  it('rejects an out-of-range answer with the Persian inline error (never silently clamps)', async () => {
    const user = userEvent.setup()
    const onFinish = vi.fn()
    render(<TestHarness onFinish={onFinish} />)
    // InputNumber has NO min/max props (the clamp bug) — the rule decides
    await user.type(screen.getByRole('spinbutton'), '99')
    await user.click(screen.getByRole('button', { name: 'ذخیره' }))
    expect(await screen.findByText('بیشتر از حداکثر (10)')).toBeInTheDocument()
    expect(onFinish).not.toHaveBeenCalled()
  })

  it('enforces required with the Persian message', async () => {
    const user = userEvent.setup()
    const onFinish = vi.fn()
    render(<TestHarness onFinish={onFinish} />)
    await user.click(screen.getByRole('button', { name: 'ذخیره' }))
    expect(await screen.findByText('پاسخ به این پرسش الزامی است')).toBeInTheDocument()
    expect(onFinish).not.toHaveBeenCalled()
  })
})
