import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import CopyNumber from './CopyNumber'

afterEach(cleanup) // vitest globals are off — no auto-cleanup

describe('CopyNumber', () => {
  it('copies the ASCII form to the clipboard on click', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } })
    render(<CopyNumber value="۰۹۱۲۱۲۳۴۵۶۷" />)
    screen.getByRole('button', { name: 'کپی' }).click()
    await vi.waitFor(() =>
      expect(writeText).toHaveBeenCalledWith('09121234567'),
    )
    vi.unstubAllGlobals()
  })

  it('renders nothing for an empty value (callers show their own dash)', () => {
    const { container } = render(<CopyNumber value={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
