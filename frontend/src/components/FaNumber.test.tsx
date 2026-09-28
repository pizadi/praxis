import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import FaNumber from './FaNumber'
import DirectedTextArea from './DirectedTextArea'

afterEach(cleanup) // vitest globals are off — no auto-cleanup

describe('FaNumber', () => {
  it('shows Persian digits as real, selectable text', () => {
    render(<FaNumber value="09121234567" />)
    expect(screen.getByText('۰۹۱۲۱۲۳۴۵۶۷')).toBeInTheDocument()
  })

  it('normalizes digits that are already Persian (formatJalali/formatMoney output)', () => {
    render(<FaNumber value="۱۴۰۳/۰۵/۱۲" />)
    expect(screen.getByText('۱۴۰۳/۰۵/۱۲')).toBeInTheDocument()
  })

  it('keeps the non-digit parts of a mixed value (money, file sizes)', () => {
    render(<FaNumber value="۵۰۰,۰۰۰ تومان" />)
    expect(screen.getByText('۵۰۰,۰۰۰ تومان')).toBeInTheDocument()
  })

  it('rewrites the clipboard to ASCII when the selection is copied', () => {
    const setData = vi.fn()
    const { container } = render(<FaNumber value="09121234567" />)
    fireEvent.copy(container.querySelector('.fa-num') as Element, {
      clipboardData: {
        getData: () => 'متن ۰۹۱۲۱۲۳۴۵۶۷',
        setData,
      },
    })
    // Persian digit characters swap to ASCII; everything else is untouched
    expect(setData).toHaveBeenCalledWith('text/plain', 'متن 09121234567')
  })

  it('leaves the clipboard alone when nothing was copied', () => {
    const setData = vi.fn()
    const { container } = render(<FaNumber value="1234" />)
    fireEvent.copy(container.querySelector('.fa-num') as Element, {
      clipboardData: { getData: () => '', setData },
    })
    expect(setData).not.toHaveBeenCalled()
  })

  it('reads left-to-right even inside RTL text', () => {
    const { container } = render(<FaNumber value="1234567890" />)
    expect(container.querySelector('.fa-num')).toHaveAttribute('dir', 'ltr')
  })

  it('renders nothing for an empty value (callers show their own dash)', () => {
    const { container } = render(<FaNumber value={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('DirectedTextArea', () => {
  it('aligns right for Persian text', () => {
    render(<DirectedTextArea value="بیمار درد قفسه سینه دارد" onChange={() => {}} />)
    const area = screen.getByRole('textbox')
    expect(area).toHaveAttribute('dir', 'rtl')
    expect(area).toHaveStyle({ textAlign: 'right' })
  })

  it('aligns left for a note that starts with a Latin letter', () => {
    render(<DirectedTextArea value="Aspirin 100mg daily" onChange={() => {}} />)
    const area = screen.getByRole('textbox')
    expect(area).toHaveAttribute('dir', 'ltr')
    expect(area).toHaveStyle({ textAlign: 'left' })
  })

  it('decides on the first LETTER, not the first character', () => {
    render(<DirectedTextArea value="1403/05/12 — بیمار مراجعه کرد" onChange={() => {}} />)
    expect(screen.getByRole('textbox')).toHaveAttribute('dir', 'rtl')
    render(<DirectedTextArea value="1403/05/12 — BP 120/80" onChange={() => {}} />)
    expect(screen.getAllByRole('textbox')[1]).toHaveAttribute('dir', 'ltr')
  })

  it('falls back to RTL for an empty field', () => {
    render(<DirectedTextArea value="" onChange={() => {}} />)
    expect(screen.getByRole('textbox')).toHaveAttribute('dir', 'rtl')
  })
})
