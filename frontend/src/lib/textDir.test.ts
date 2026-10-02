import { describe, expect, it } from 'vitest'

import { textAlign, textDirection } from './textDir'

describe('textDirection', () => {
  it('is rtl when the first letter is Persian/Arabic', () => {
    expect(textDirection('بیمار درد دارد')).toBe('rtl')
    expect(textDirection('كarta')).toBe('rtl') // Arabic kaf
  })

  it('is ltr when the first letter is Latin', () => {
    expect(textDirection('Aspirin 100mg')).toBe('ltr')
    expect(textDirection('WBC: 12000')).toBe('ltr')
  })

  it('ignores digits, punctuation and whitespace before the first letter', () => {
    expect(textDirection('1403/05/12 — بیمار')).toBe('rtl')
    expect(textDirection('   12,5 mg')).toBe('ltr')
    expect(textDirection('\n\t- Aspirin')).toBe('ltr')
  })

  it('looks past a bracketed Latin abbreviation — the rule is the FIRST letter', () => {
    // "(BP)" starts with a Latin B, so the note reads LTR even though the rest
    // is Persian. Documented behaviour, not an accident.
    expect(textDirection('(BP) 120/80 — بیمار')).toBe('ltr')
  })

  it('is rtl for Hebrew and other RTL scripts', () => {
    expect(textDirection('שלום')).toBe('rtl')
  })

  it('defaults to rtl when there is no letter at all', () => {
    expect(textDirection('')).toBe('rtl')
    expect(textDirection('123 456')).toBe('rtl')
    expect(textDirection('...')).toBe('rtl')
    expect(textDirection(null)).toBe('rtl')
    expect(textDirection(undefined)).toBe('rtl')
  })

  it('decides on the FIRST letter, not the first strong character overall', () => {
    // a leading Latin brand name decides, even though Persian follows
    expect(textDirection('Metformin بیمار دیابت')).toBe('ltr')
  })

  it('handles a non-Latin RTL script with a surrogate pair (outside the BMP)', () => {
    expect(textDirection('𐤀𐤁𐤂')).toBe('ltr') // Old Italic — not RTL
  })
})

describe('textAlign', () => {
  it('follows the direction', () => {
    expect(textAlign('rtl')).toBe('right')
    expect(textAlign('ltr')).toBe('left')
  })
})
