// Questionnaire format/response helpers (mirror backend app/services/questionnaires.py
// and app/services/scoring.py — keep the two in sync)
import type { Rule } from 'antd/es/form'

export interface NumberQuestion {
  key: string
  label: string
  type: 'number'
  required: boolean
  min: number | null
  max: number | null
  integer: boolean
  unit: string
}

export interface ChoiceOption {
  value: string
  label: string
  score: number | null
}

export interface ChoiceQuestion {
  key: string
  label: string
  type: 'choice'
  required: boolean
  options: ChoiceOption[]
}

export interface StringQuestion {
  key: string
  label: string
  type: 'string'
  required: boolean
  multiline: boolean
  max_length: number
}

export type Question = NumberQuestion | ChoiceQuestion | StringQuestion

export interface FormatDoc {
  version: number
  title: string
  questions: Question[]
  /** optional arithmetic formula over question keys for the total score */
  score_formula?: string
}

export type AnswerValue = number | string | null

export type Answers = Record<string, AnswerValue>

// --- rendering merge (no snapshot: current template vs stored answers) --------

export type CellStatus = 'ok' | 'missing' | 'invalid'

export interface MergedCell {
  question: Question
  value: AnswerValue | undefined
  status: CellStatus
  /** short Persian explanation for invalid values */
  reason: string
}

export interface MergedResponse {
  rows: MergedCell[]
  /** answer keys the current template no longer knows (ignored on render) */
  unknownKeys: string[]
  /** keys whose values are invalid against the current format (clearable) */
  invalidKeys: string[]
  /** whether the template defines a score at all (formula or choice scores) */
  scored: boolean
  /** total score (null when scoring exists but is not computable) */
  totalScore: number | null
}

export function hasFormula(format: FormatDoc): boolean {
  return !!format.score_formula?.trim()
}

/** Persian message for a backend answer-validation error string. */
export function faAnswerError(msg: string): string {
  const between = msg.match(/^must be between (.+) and (.+)$/)
  if (between) return `باید بین ${between[1]} و ${between[2]} باشد`
  switch (msg) {
    case 'must be a number':
      return 'مقدار عددی نیست'
    case 'must be an integer':
      return 'باید عدد صحیح باشد'
    case 'must be one of the listed options':
      return 'گزینه نامعتبر'
    case 'unknown question key':
      return 'کلید پرسش در قالب موجود نیست'
  }
  if (msg.startsWith('max length ')) return `حداکثر طول ${msg.slice(11)}`
  return msg
}

function invalidReason(q: Question, v: AnswerValue): string {
  if (q.type === 'number') {
    if (typeof v !== 'number' || Number.isNaN(v)) return 'مقدار عددی نیست'
    if (q.integer && !Number.isInteger(v)) return 'باید عدد صحیح باشد'
    if (q.min != null && v < q.min) return `کمتر از حداقل (${q.min})`
    if (q.max != null && v > q.max) return `بیشتر از حداکثر (${q.max})`
    return ''
  }
  if (q.type === 'choice') {
    return q.options.some((o) => o.value === v) ? '' : 'گزینه نامعتبر'
  }
  if (typeof v !== 'string') return 'مقدار متنی نیست'
  return v.length > q.max_length ? `حداکثر طول ${q.max_length}` : ''
}

/** antd form rules for a question (used by the fill form): required plus a
 * full value check (range/integer/choice/length) with Persian messages. */
export function questionRule(q: Question): Rule[] {
  const rules: Rule[] = q.required
    ? [{ required: true, message: 'پاسخ به این پرسش الزامی است' }]
    : []
  rules.push({
    validator: async (_rule: unknown, value: unknown) => {
      if (value === undefined || value === null || value === '') return
      const reason = invalidReason(q, value as AnswerValue)
      if (reason) throw new Error(reason)
    },
  })
  return rules
}

// --- score formula (mirror backend app/services/scoring.py) ---------------------

type FNode =
  | { k: 'num'; v: number }
  | { k: 'ref'; key: string }
  | { k: 'un'; op: '+' | '-'; operand: FNode }
  | { k: 'bin'; op: '+' | '-' | '*' | '/'; left: FNode; right: FNode }
  | { k: 'call'; name: 'min' | 'max' | 'abs'; args: FNode[] }

type FToken = { kind: 'num' | 'ident' | 'op'; value: number | string }

const FA_NUM_RE = /^\d+(?:\.\d+)?$/

function tokenizeFormula(text: string): FToken[] {
  const tokens: FToken[] = []
  let i = 0
  while (i < text.length) {
    const ch = text[i]
    if (/\s/.test(ch)) {
      i += 1
      continue
    }
    if ('+-*/(),'.includes(ch)) {
      tokens.push({ kind: 'op', value: ch })
      i += 1
      continue
    }
    const m = /^[A-Za-z0-9_]+/.exec(text.slice(i))
    if (!m) throw new Error(`unexpected character '${ch}'`)
    let word = m[0]
    i += word.length
    // decimal literal like 2.5 — the dot is not a word character
    if (/^\d+$/.test(word) && text[i] === '.' && /\d/.test(text[i + 1] ?? '')) {
      const dot = /^\.\d+/.exec(text.slice(i))
      if (dot) {
        word += dot[0]
        i += dot[0].length
      }
    }
    if (FA_NUM_RE.test(word)) tokens.push({ kind: 'num', value: Number(word) })
    else tokens.push({ kind: 'ident', value: word })
  }
  return tokens
}

class FormulaParser {
  private toks: FToken[]
  private pos = 0

  constructor(toks: FToken[]) {
    this.toks = toks
  }

  private peek(): FToken | null {
    return this.pos < this.toks.length ? this.toks[this.pos] : null
  }

  parse(): FNode {
    if (this.toks.length === 0) throw new Error('فرمول خالی است')
    const node = this.expr()
    if (this.pos !== this.toks.length) throw new Error('نشانه اضافی در فرمول')
    return node
  }

  private expectOp(op: string): void {
    const t = this.peek()
    if (!t || t.kind !== 'op' || t.value !== op) throw new Error(`«${op}» انتظار می‌رفت`)
    this.pos += 1
  }

  private expr(): FNode {
    let node = this.term()
    for (;;) {
      const t = this.peek()
      if (t && t.kind === 'op' && (t.value === '+' || t.value === '-')) {
        this.pos += 1
        node = { k: 'bin', op: t.value, left: node, right: this.term() }
      } else {
        return node
      }
    }
  }

  private term(): FNode {
    let node = this.factor()
    for (;;) {
      const t = this.peek()
      if (t && t.kind === 'op' && (t.value === '*' || t.value === '/')) {
        this.pos += 1
        node = { k: 'bin', op: t.value, left: node, right: this.factor() }
      } else {
        return node
      }
    }
  }

  private factor(): FNode {
    const t = this.peek()
    if (!t) throw new Error('فرمول ناتمام است')
    if (t.kind === 'num') {
      this.pos += 1
      return { k: 'num', v: t.value as number }
    }
    if (t.kind === 'op' && t.value === '(') {
      this.pos += 1
      const node = this.expr()
      this.expectOp(')')
      return node
    }
    if (t.kind === 'op' && (t.value === '+' || t.value === '-')) {
      this.pos += 1
      return { k: 'un', op: t.value, operand: this.factor() }
    }
    if (t.kind === 'ident') {
      this.pos += 1
      const name = t.value as string
      const next = this.peek()
      if (['min', 'max', 'abs'].includes(name) && next && next.kind === 'op' && next.value === '(') {
        return this.call(name as 'min' | 'max' | 'abs')
      }
      return { k: 'ref', key: name }
    }
    throw new Error(`نشانه نامعتبر: ${String(t.value)}`)
  }

  private call(name: 'min' | 'max' | 'abs'): FNode {
    this.expectOp('(')
    const args: FNode[] = [this.expr()]
    for (;;) {
      const t = this.peek()
      if (t && t.kind === 'op' && t.value === ',') {
        this.pos += 1
        args.push(this.expr())
      } else {
        break
      }
    }
    this.expectOp(')')
    if (name === 'abs' && args.length !== 1) throw new Error('abs() دقیقاً یک آرگومان می‌گیرد')
    if (args.length < 1) throw new Error(`${name}() حداقل یک آرگومان می‌گیرد`)
    return { k: 'call', name, args }
  }
}

function parseFormula(text: string): FNode {
  return new FormulaParser(tokenizeFormula(text)).parse()
}

function collectRefs(node: FNode, out: string[]): void {
  if (node.k === 'ref') out.push(node.key)
  else if (node.k === 'un') collectRefs(node.operand, out)
  else if (node.k === 'bin') {
    collectRefs(node.left, out)
    collectRefs(node.right, out)
  } else if (node.k === 'call') node.args.forEach((a) => collectRefs(a, out))
}

/** Client-side mirror of the backend formula validation (server is
 * authoritative): returns null when valid, else a Persian error message.
 * Accepts the loose builder question shape too (only key+type matter). */
export function validateFormulaText(
  text: string,
  questions: { key: string; type: 'number' | 'choice' | 'string' }[],
): string | null {
  const trimmed = (text ?? '').trim()
  if (!trimmed) return null
  let ast: FNode
  try {
    ast = parseFormula(trimmed)
  } catch (e) {
    return e instanceof Error ? e.message : 'فرمول نامعتبر است'
  }
  const refs: string[] = []
  collectRefs(ast, refs)
  for (const key of refs) {
    const q = questions.find((x) => x.key === key)
    if (!q) return `کلید ناشناس در فرمول: ${key}`
    if (q.type === 'string') return `پرسش متنی در فرمول قابل استفاده نیست: ${key}`
  }
  return null
}

function operandValue(format: FormatDoc, key: string, answers: Answers): number | null {
  const q = format.questions?.find((x) => x.key === key)
  if (!q) return null
  const v = answers?.[key]
  if (q.type === 'number') {
    return typeof v === 'number' && !Number.isNaN(v) ? v : null
  }
  if (q.type === 'choice') {
    if (typeof v !== 'string') return null
    const opt = q.options.find((o) => o.value === v)
    return opt && typeof opt.score === 'number' ? opt.score : null
  }
  return null
}

function evalNode(node: FNode, format: FormatDoc, answers: Answers): number | null {
  switch (node.k) {
    case 'num':
      return node.v
    case 'ref':
      return operandValue(format, node.key, answers)
    case 'un': {
      const v = evalNode(node.operand, format, answers)
      return v === null ? null : node.op === '-' ? -v : v
    }
    case 'bin': {
      const l = evalNode(node.left, format, answers)
      const r = evalNode(node.right, format, answers)
      if (l === null || r === null) return null
      if (node.op === '+') return l + r
      if (node.op === '-') return l - r
      if (node.op === '*') return l * r
      return r === 0 ? null : l / r
    }
    case 'call': {
      const vals: number[] = []
      for (const a of node.args) {
        const v = evalNode(a, format, answers)
        if (v === null) return null
        vals.push(v)
      }
      if (node.name === 'abs') return Math.abs(vals[0])
      return node.name === 'min' ? Math.min(...vals) : Math.max(...vals)
    }
  }
}

/** Total score from the template formula; null when no formula exists or it
 * cannot be computed (missing/invalid referenced answer, division by zero). */
export function evaluateFormula(format: FormatDoc, answers: Answers): number | null {
  const text = (format.score_formula ?? '').trim()
  if (!text) return null
  try {
    return evalNode(parseFormula(text), format, answers)
  } catch {
    return null
  }
}

export function mergeResponse(format: FormatDoc, answers: Answers): MergedResponse {
  const rows: MergedCell[] = []
  const invalidKeys: string[] = []

  for (const q of format.questions ?? []) {
    const v = answers?.[q.key]
    if (v === undefined || v === null) {
      rows.push({ question: q, value: v, status: 'missing', reason: '' })
      continue
    }
    const bad = invalidReason(q, v)
    if (bad) {
      rows.push({ question: q, value: v, status: 'invalid', reason: bad })
      invalidKeys.push(q.key)
    } else {
      rows.push({ question: q, value: v, status: 'ok', reason: '' })
    }
  }

  const unknownKeys = Object.keys(answers ?? {}).filter(
    (k) => !new Set((format.questions ?? []).map((q) => q.key)).has(k),
  )

  if (hasFormula(format)) {
    return { rows, unknownKeys, invalidKeys, scored: true, totalScore: evaluateFormula(format, answers) }
  }
  // no formula: fall back to the sum of chosen (valid) option scores
  let hasScores = false
  let totalScore = 0
  for (const row of rows) {
    if (row.status !== 'ok' || row.question.type !== 'choice') continue
    const opt = row.question.options.find((o) => o.value === row.value)
    if (opt && typeof opt.score === 'number') {
      hasScores = true
      totalScore += opt.score
    }
  }
  return { rows, unknownKeys, invalidKeys, scored: hasScores, totalScore: hasScores ? totalScore : null }
}
