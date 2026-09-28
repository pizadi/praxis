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
    const num = container.querySelector('.fa-num') as Element
    // a REAL selection over the digits (as a user's drag would make) — the
    // hook reads sel.toString(): Chromium returns '' from clipboardData
    // getData() inside a copy event
    const range = document.createRange()
    range.selectNodeContents(num)
    const sel = document.getSelection()
    sel?.removeAllRanges()
    sel?.addRange(range)
    fireEvent.copy(num, {
      clipboardData: { setData },
    })
    expect(setData).toHaveBeenCalledWith('text/plain', '09121234567')
  })

  it('catches copies whose selection merely intersects the number (drag starts outside)', () => {
    const setData = vi.fn()
    const { container } = render(
      <div>
        <span>before </span>
        <FaNumber value="0912" />
      </div>,
    )
    const outer = container.querySelector('div') as Element
    // drag from the surrounding text INTO the number: the copy event fires at
    // the ancestor div, not at the number's span
    const range = document.createRange()
    range.selectNodeContents(outer)
    const sel = document.getSelection()
    sel?.removeAllRanges()
    sel?.addRange(range)
    fireEvent.copy(outer, { clipboardData: { setData } })
    expect(setData).toHaveBeenCalledWith('text/plain', 'before 0912')
  })

  it('leaves copies of ordinary text alone', () => {
    const setData = vi.fn()
    render(
      <div>
        <span>متن بدون رقم</span>
      </div>,
    )
    const span = document.querySelector('span') as Element
    const range = document.createRange()
    range.selectNodeContents(span)
    const sel = document.getSelection()
    sel?.removeAllRanges()
    sel?.addRange(range)
    fireEvent.copy(span, { clipboardData: { setData } })
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
