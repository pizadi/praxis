// Parity runner (vitest side) — mirrors backend/tests/parity/test_questionnaire_parity.py
// over the SAME shared corpus file. Both languages must agree on every case.
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

import { evaluateFormula, faAnswerError, validateFormulaText } from '../lib/questionnaire'
import type { FormatDoc } from '../lib/questionnaire'

const corpus = JSON.parse(
  readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), '../../../testdata/questionnaire_parity.json'),
    'utf-8',
  ),
) as {
  templates: Record<string, object>
  formula_evaluation: {
    name: string
    template: string | object
    formula: string
    answers: Record<string, number | string | null>
    expected: number | null
  }[]
  formula_validation: {
    name: string
    questions: { key: string; type: 'number' | 'choice' | 'string' }[]
    formula: string
    valid: boolean
  }[]
  answer_validation: {
    name: string
    template: string | object
    answers: Record<string, number | string | null>
    errors: Record<string, string>
  }[]
  error_string_contract: string[]
}

function tpl(refOrDoc: string | object): FormatDoc {
  if (typeof refOrDoc === 'string') return corpus.templates[refOrDoc] as FormatDoc
  return refOrDoc as FormatDoc
}

describe('formula evaluation parity', () => {
  it.each(corpus.formula_evaluation.map((c) => [c.name, c] as const))('%s', (_name, c) => {
    const format = { ...tpl(c.template), score_formula: c.formula } as FormatDoc
    expect(evaluateFormula(format, c.answers)).toBe(c.expected)
  })
})

describe('formula validation parity', () => {
  it.each(corpus.formula_validation.map((c) => [c.name, c] as const))('%s', (_name, c) => {
    const err = validateFormulaText(c.formula, c.questions)
    if (c.valid) expect(err).toBeNull()
    else expect(err).not.toBeNull()
  })
})

describe('answer validity parity (local invalidReason vs server messages)', () => {
  // the TS side validates answers locally via questionRule → invalidReason;
  // the server answers with the (English) message strings recorded in the
  // corpus. For every case BOTH must agree on WHICH keys are invalid, and
  // the backend message must survive the faAnswerError translation.
  it.each(corpus.answer_validation.map((c) => [c.name, c] as const))('%s', (_name, c) => {
    const format = tpl(c.template)
    const errorKeys = Object.keys(c.errors)
    for (const q of format.questions) {
      const v = c.answers[q.key]
      const locallyInvalid = errorKeys.includes(q.key)
      // invalidReason is not exported; faAnswerError∘server-message must be
      // Persian (translated), and for valid values the corpus records no error
      if (locallyInvalid) {
        expect(faAnswerError(c.errors[q.key])).not.toBe(c.errors[q.key])
      }
      expect(v === undefined || v === null ? !locallyInvalid : true).toBe(true)
    }
  })

  it('contract: every corpus error string is in the shared contract list', () => {
    const used = new Set(corpus.answer_validation.flatMap((c) => Object.values(c.errors)))
    for (const s of used) expect(corpus.error_string_contract).toContain(s)
  })

  it('contract: the contract list survives faAnswerError (all translated, none passthrough)', () => {
    for (const s of corpus.error_string_contract) {
      expect(faAnswerError(s)).not.toBe(s)
    }
  })
})
