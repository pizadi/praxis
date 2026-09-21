import { describe, expect, it } from 'vitest'

import { fileSize, formatMoney, toEnDigits, toFaDigits } from './jalali'

describe('digit conversion', () => {
  it('converts ASCII digits to Persian', () => {
    expect(toFaDigits('09121234567')).toBe('۰۹۱۲۱۲۳۴۵۶۷')
    expect(toFaDigits(1405)).toBe('۱۴۰۵')
    expect(toFaDigits('a1b2')).toBe('a۱b۲')
  })

  it('normalizes Persian AND Arabic digits to ASCII (typed inputs)', () => {
    expect(toEnDigits('۰۱۲۳۴۵۶۷۸۹')).toBe('0123456789')
    expect(toEnDigits('٠١٢٣٤٥٦٧٨٩')).toBe('0123456789')
    expect(toEnDigits('mixed ۵ text')).toBe('mixed 5 text')
    expect(toEnDigits('plain')).toBe('plain')
  })
})

describe('formatMoney', () => {
  it('thousands-separates (en-US comma) then Persian-izes the digits', () => {
    expect(formatMoney(500000)).toBe('۵۰۰,۰۰۰')
  })
})

describe('fileSize', () => {
  it('uses the right unit, Persian digits (ASCII decimal dot), dash for null', () => {
    expect(fileSize(null)).toBe('-')
    expect(fileSize(12)).toBe('۱۲ بایت')
    expect(fileSize(2048)).toBe('۲.۰ کیلوبایت')
    expect(fileSize(3 * 1024 * 1024)).toBe('۳.۰ مگابایت')
  })
})
