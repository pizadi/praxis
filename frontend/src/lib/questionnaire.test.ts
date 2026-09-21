import { describe, expect, it } from 'vitest'
import type { Rule } from 'antd/es/form'

import {
  evaluateFormula,
  hasFormula,
  mergeResponse,
  questionRule,
  rangeHint,
  type ChoiceQuestion,
  type FormatDoc,
  type NumberQuestion,
} from './questionnaire'

/** The last rule is always the value-check validator. */
function ruleValidator(rules: Rule[]): (r: unknown, v: unknown) => Promise<void> {
  return (rules[rules.length - 1] as unknown as { validator: (r: unknown, v: unknown) => Promise<void> })
    .validator
}

const NUMBER_Q = {
  key: 'a',
  label: 'A',
  type: 'number',
  required: true,
  min: 0,
  max: 10,
  integer: true,
  unit: '',
} as NumberQuestion
const CHOICE_Q = {
  key: 'c',
  label: 'C',
  type: 'choice',
  required: false,
  options: [
    { value: 'bad', label: 'بد', score: 0 },
    { value: 'good', label: 'خوب', score: 2 },
    { value: 'meh', label: 'م sig', score: null },
  ],
} as ChoiceQuestion
const STRING_Q = { key: 's', label: 'S', type: 'string', required: false, multiline: false, max_length: 5 }

const NO_FORMULA = { version: 1, title: 't', questions: [NUMBER_Q, CHOICE_Q, STRING_Q] } as FormatDoc
const WITH_FORMULA = { ...NO_FORMULA, score_formula: 'a * 2 + c' } as FormatDoc

describe('hasFormula', () => {
  it('detects formulas', () => {
    expect(hasFormula(WITH_FORMULA)).toBe(true)
    expect(hasFormula(NO_FORMULA)).toBe(false)
    expect(hasFormula({ ...NO_FORMULA, score_formula: '   ' })).toBe(false)
  })
})

describe('questionRule', () => {
  const rule = questionRule(NUMBER_Q)
  const validator = ruleValidator(rule)

  it('accepts valid / null / absent (null is ALWAYS valid — required is UI-level)', async () => {
    await expect(validator({}, 5)).resolves.toBeUndefined()
    await expect(validator({}, null)).resolves.toBeUndefined()
    await expect(validator({}, undefined)).resolves.toBeUndefined()
  })

  it('rejects out-of-range / non-integer / wrong type with Persian messages', async () => {
    await expect(validator({}, 11)).rejects.toThrow('بیشتر از حداکثر (10)')
    await expect(validator({}, -1)).rejects.toThrow('کمتر از حداقل (0)')
    await expect(validator({}, 1.5)).rejects.toThrow('باید عدد صحیح باشد')
    await expect(validator({}, '5')).rejects.toThrow('مقدار عددی نیست')
  })

  it('empty string is skipped (the form treats it as untouched)', async () => {
    await expect(validator({}, '')).resolves.toBeUndefined()
  })

  it('required rule carries the Persian message', () => {
    expect((rule[0] as { message?: string }).message).toBe('پاسخ به این پرسش الزامی است')
  })

  it('choice rule rejects unknown options', async () => {
    const v = ruleValidator(questionRule(CHOICE_Q))
    await expect(v({}, 'nope')).rejects.toThrow('گزینه نامعتبر')
    await expect(v({}, 'good')).resolves.toBeUndefined()
  })
})

describe('rangeHint', () => {
  it('renders ≥/≤ hints for the bounds', () => {
    expect(rangeHint(NUMBER_Q)).toBe('≥0 ≤10')
    expect(rangeHint({ ...NUMBER_Q, max: null })).toBe('≥0')
    expect(rangeHint({ ...NUMBER_Q, min: null })).toBe('≤10')
    expect(rangeHint({ ...NUMBER_Q, min: null, max: null })).toBe('')
  })
})

describe('mergeResponse (no snapshot: current template vs stored answers)', () => {
  it('marks ok/missing/invalid and collects invalid + unknown keys', () => {
    const merged = mergeResponse(WITH_FORMULA, { a: 200, old_key: 1, s: null })
    const byKey = Object.fromEntries(merged.rows.map((r) => [r.question.key, r.status]))
    expect(byKey).toEqual({ a: 'invalid', c: 'missing', s: 'missing' })
    expect(merged.invalidKeys).toEqual(['a'])
    expect(merged.unknownKeys).toEqual(['old_key'])
  })

  it('computes the formula score; null when an operand is unresolvable', () => {
    expect(mergeResponse(WITH_FORMULA, { a: 3, c: 'good' }).totalScore).toBe(8)
    expect(mergeResponse(WITH_FORMULA, { a: 3 }).totalScore).toBeNull() // c missing
    expect(mergeResponse(WITH_FORMULA, { c: 'good' }).totalScore).toBeNull() // a missing
  })

  it('without a formula: falls back to the sum of chosen option scores', () => {
    const merged = mergeResponse(NO_FORMULA, { c: 'good', a: 5 })
    expect(merged.scored).toBe(true)
    expect(merged.totalScore).toBe(2)
  })

  it('unscored choices (null score) never invent a score', () => {
    const merged = mergeResponse(NO_FORMULA, { c: 'meh' })
    expect(merged.scored).toBe(false)
    expect(merged.totalScore).toBeNull()
  })
})

describe('evaluateFormula', () => {
  it('returns null for a missing formula', () => {
    expect(evaluateFormula(NO_FORMULA, { a: 1 })).toBeNull()
  })
  it('evaluates over choice scores and numbers', () => {
    expect(evaluateFormula(WITH_FORMULA, { a: 3, c: 'good' })).toBe(8)
    expect(evaluateFormula(WITH_FORMULA, { a: 3, c: 'meh' })).toBeNull() // no score
  })
  it('never divides by zero', () => {
    const f = { ...NO_FORMULA, score_formula: 'a / 0' } as FormatDoc
    expect(evaluateFormula(f, { a: 1 })).toBeNull()
  })
})
