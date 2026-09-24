# Questionnaires

## Templates

Admin-defined templates (`/questionnaires`, perm `questionnaires.templates`)
whose `format_json` is a validated JSON document:

```json
{
  "version": 1,
  "title": "پرسش‌نامه درد",
  "score_formula": "0.5 * pain_level + mobility",
  "questions": [
    {"key": "pain_level", "label": "شدت درد", "type": "number",
     "required": true, "min": 0, "max": 10, "integer": true, "unit": ""},
    {"key": "mobility", "label": "تحرک", "type": "choice", "required": false,
     "options": [{"value": "bad", "label": "بد", "score": 0},
                 {"value": "ok", "label": "متوسط", "score": 1}]},
    {"key": "notes", "label": "توضیحات", "type": "string",
     "required": false, "multiline": true, "max_length": 500}
  ]
}
```

- Question types: `number` (min/max/integer/unit), `choice` (2–50 options,
  each with an optional `score`), `string` (multiline, max_length).
- Keys `^[a-z0-9_]{1,64}$`, unique per template; `extra="forbid"` on every
  level; validated by pydantic `QuestionnaireFormat`
  (`app/services/questionnaires.py`).
- Every write path — API create/update, the graphical builder, and **JSON
  upload** — funnels through the same validation;
  `POST /questionnaires/templates/validate` checks without saving. The UI
  uploads JSON by parsing it in the browser (`File.text()` + `JSON.parse`)
  and posting the object — raw files never hit the API.
- Inserting a question at the **start** or **between** existing questions:
  a small plus button appears when hovering the gap above each question
  card (the trailing «پرسش جدید» button appends at the end).

## Responses

- Belong to a **patient** (not an appointment); multiple responses per
  template allowed; created/edited from the patient page (perm
  `questionnaires.fill`).
- `answers_json` stores raw nullable JSON. Server-side validation rejects
  unknown keys and type/range/choice violations only — **null/absent is
  always valid** (`required` is a UI-level constraint). 422s carry
  `details.fields` per-key errors, which the UI feeds back inline
  (`apiFieldErrors` → `form.setFields`).
- The fill form validates via antd rules from `questionRule()` — do NOT
  reintroduce `InputNumber min/max/precision` props there: they silently
  clamp values (the "validation doesn't work" bug).
- **No snapshot**: rendering merges stored answers with the *current*
  template (`frontend/src/lib/questionnaire.ts::mergeResponse`) — removed
  keys are ignored, new questions render null, invalid values render
  "missing" with a warning banner + a confirm-dialog clear (a PATCH that is
  re-validated server-side).

## Scoring

- `score_formula` lives inside `format_json` (no migration): a small
  arithmetic expression over question keys — `+ - * /`, parentheses, numeric
  literals, and the functions `min`/`max` (1+ args) and `abs` (1 arg).
- A `number` question contributes its answer; a `choice` question the chosen
  option's score. Syntax and references are validated at template save
  (referenced keys must exist and be number/choice questions).
- Parser/evaluator: `app/services/scoring.py` (tokenizer + recursive-descent
  AST — **never `eval`**). Formula validation is server-authoritative: the
  builder debounces `POST /questionnaires/formulas/validate`. The TypeScript
  mirror retains only the evaluator used to render accepted templates.
- **Sync is enforced by a shared corpus**:
  `testdata/questionnaire_parity.json` (evaluation totals, formula validation
  outcomes, answer error strings, format matrix) is executed by the pytest
  runner (`backend/tests/parity/`) for validation and by both runners for
  evaluation/answers. It pins the length/depth limits
  (`MAX_FORMULA_LENGTH = 1000`, `MAX_DEPTH = 100`), the error-message
  contract with `faAnswerError`, and the whitespace-only formula rule (the
  value is trimmed at validation — blank means "no scoring"). Change the
  server validator only together with the corpus and runners.
- Evaluation is **total**: any missing/invalid referenced answer, a chosen
  option without a score, or division by zero → the total is `None`,
  rendered as "—". A score is never invented.
- Without a formula, the total falls back to the sum of the chosen options'
  scores.

## Responses report

- `/questionnaire-responses` (گزارش پاسخ‌ها, menu gated by
  `questionnaires.read`): pick a template → every response in a
  horizontally scrollable table (`scroll={{ x: 'max-content' }}`) — patient
  national ID, Jalali date, one column per question, total score when the
  template defines scoring.
- API: `GET /questionnaires/responses?template_id=` →
  `Page[QuestionnaireResponseReportOut]` (adds `patient_national_id`);
  multi-column select → **`paginate_rows`**, not `paginate`. Subtree
  filtered: live response + patient + template (deleted template → 404).
- **CSV is generated client-side** (all pages fetched with a cap, UTF-8
  BOM, proper quoting) so Excel renders Persian correctly.
