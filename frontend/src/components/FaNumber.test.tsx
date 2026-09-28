import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import FaNumber from './FaNumber'
import DirectedTextArea from './DirectedTextArea'

afterEach(cleanup) // vitest globals are off — no auto-cleanup

describe('FaNumber', () => {
  it('shows Persian digits but exposes ASCII in the DOM (what a copy yields)', () => {
    render(<FaNumber value="09121234567" />)
    // the copyable layer is the ASCII text
    expect(screen.getByText('09121234567')).toBeInTheDocument()
    // the visible overlay is Persian
    expect(document.querySelector('.fa-num-fa')?.textContent).toBe('۰۹۱۲۱۲۳۴۵۶۷')
  })

  it('normalizes digits that are already Persian (formatJalali/formatMoney output)', () => {
    render(<FaNumber value="۱۴۰۳/۰۵/۱۲" />)
    expect(screen.getByText('1403/05/12')).toBeInTheDocument()
    expect(document.querySelector('.fa-num-fa')?.textContent).toBe('۱۴۰۳/۰۵/۱۲')
  })

  it('keeps the non-digit parts of a mixed value (money, file sizes)', () => {
    render(<FaNumber value="۵۰۰,۰۰۰ تومان" />)
    expect(screen.getByText(/500,000/)).toBeInTheDocument()
    expect(document.querySelector('.fa-num-fa')?.textContent).toBe('۵۰۰,۰۰۰ تومان')
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
