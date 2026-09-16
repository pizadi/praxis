// Questionnaire format/response helpers (mirror backend app/services/questionnaires.py)

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
  /** sum of scores of valid chosen options (null when no scores exist) */
  totalScore: number | null
}

export function mergeResponse(format: FormatDoc, answers: Answers): MergedResponse {
  const rows: MergedCell[] = []
  const invalidKeys: string[] = []
  let hasScores = false
  let totalScore = 0

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
      if (q.type === 'choice') {
        const opt = q.options.find((o) => o.value === v)
        if (opt && typeof opt.score === 'number') {
          hasScores = true
          totalScore += opt.score
        }
      }
    }
  }

  const knownKeys = new Set((format.questions ?? []).map((q) => q.key))
  const unknownKeys = Object.keys(answers ?? {}).filter((k) => !knownKeys.has(k))
  return { rows, unknownKeys, invalidKeys, totalScore: hasScores ? totalScore : null }
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
  return typeof v === 'string' ? '' : 'مقدار متنی نیست'
}

/** antd form rules for a question (used by the fill form). */
export function questionRule(q: Question) {
  return q.required
    ? [{ required: true, message: 'پاسخ به این پرسش الزامی است' }]
    : []
}
