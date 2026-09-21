import { useEffect, useMemo } from 'react'
import {
  Alert,
  Button,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Radio,
  Space,
  Typography,
  theme,
  type FormInstance,
} from 'antd'
import { ClearOutlined, EditOutlined } from '@ant-design/icons'

import type { Answers, FormatDoc, Question } from '../lib/questionnaire'
import { mergeResponse, questionRule, rangeHint } from '../lib/questionnaire'
import { toEnDigits } from '../lib/jalali'

/**
 * Read-only rendering of a saved response merged against the CURRENT
 * template: removed questions ignored, new questions null, invalid values
 * shown as missing with a warning + clear-invalid action (PATCH).
 */
export function QuestionnaireView({
  format,
  answers,
  onClearInvalid,
  onEdit,
  clearing,
}: {
  format: FormatDoc
  answers: Answers
  onClearInvalid?: () => void
  onEdit?: () => void
  clearing?: boolean
}) {
  const merged = useMemo(() => mergeResponse(format, answers), [format, answers])

  if (merged.invalidKeys.length > 0) {
    return (
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Alert
          type="warning"
          showIcon
          message={`${merged.invalidKeys.length} پاسخ با قالب فعلی پرسش‌نامه ناسازگار است`}
          description={
            <Space direction="vertical" size={4}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                پاسخ‌های نامعتبر به‌صورت خالی نمایش داده می‌شوند. با پاک‌سازی، آن فیلدها خالی
                می‌شوند (پاسخ‌های معتبر حفظ می‌شوند).
              </Typography.Text>
              {onClearInvalid && (
                <Popconfirm
                  title="فیلدهای نامعتبر پاک شوند؟"
                  description="پاسخ‌های معتبر حفظ می‌شوند و این عمل قابل بازگشت نیست مگر با ویرایش مجدد."
                  onConfirm={onClearInvalid}
                >
                  <Button size="small" icon={<ClearOutlined />} loading={clearing}>
                    پاک‌سازی فیلدهای نامعتبر
                  </Button>
                </Popconfirm>
              )}
            </Space>
          }
        />
        {onEdit && (
          <div>
            <Button size="small" icon={<EditOutlined />} onClick={onEdit}>
              ویرایش پاسخ‌ها
            </Button>
          </div>
        )}
        <QuestionnaireCells merged={merged} />
      </Space>
    )
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      {onEdit && (
        <div>
          <Button size="small" icon={<EditOutlined />} onClick={onEdit}>
            ویرایش پاسخ‌ها
          </Button>
        </div>
      )}
      <QuestionnaireCells merged={merged} />
    </Space>
  )
}

function QuestionnaireCells({ merged }: { merged: ReturnType<typeof mergeResponse> }) {
  return (
    <Descriptions bordered column={1} size="small" styles={{ label: { width: '40%' } }}>
      {merged.rows.map((row) => (
        <Descriptions.Item key={row.question.key} label={row.question.label}>
          {row.status === 'missing' && <Typography.Text type="secondary">—</Typography.Text>}
          {row.status === 'invalid' && (
            <Typography.Text type="warning">
              نامعتبر ({row.reason})
              {row.value !== null && row.value !== undefined && (
                <Typography.Text type="secondary" style={{ marginInlineStart: 8, fontSize: 12 }}>
                  مقدار ذخیره‌شده: {String(row.value)}
                </Typography.Text>
              )}
            </Typography.Text>
          )}
          {row.status === 'ok' && <ValueText question={row.question} value={row.value} />}
        </Descriptions.Item>
      ))}
      {merged.unknownKeys.length > 0 && (
        <Descriptions.Item label="پرسش‌های حذف‌شده">
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {merged.unknownKeys.length} پاسخ مربوط به پرسش‌هایی که دیگر در قالب نیستند (نادیده
            گرفته می‌شوند)
          </Typography.Text>
        </Descriptions.Item>
      )}
      {merged.scored && (
        <Descriptions.Item label="جمع نمره">
          {merged.totalScore !== null ? (
            <Typography.Text strong>{merged.totalScore}</Typography.Text>
          ) : (
            <Typography.Text type="secondary">
              — (پاسخ همهٔ پرسش‌های مؤثر بر نمره لازم است)
            </Typography.Text>
          )}
        </Descriptions.Item>
      )}
    </Descriptions>
  )
}

function ValueText({ question, value }: { question: Question; value: unknown }) {
  if (value === null || value === undefined || value === '') {
    return <Typography.Text type="secondary">—</Typography.Text>
  }
  if (question.type === 'choice') {
    const opt = question.options.find((o) => o.value === value)
    if (!opt) return String(value)
    return (
      <Space size={8}>
        <span>{opt.label}</span>
        {typeof opt.score === 'number' && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            نمره: {opt.score}
          </Typography.Text>
        )}
      </Space>
    )
  }
  if (question.type === 'number') {
    return (
      <span>
        {String(value)}
        {question.unit ? ` ${question.unit}` : ''}
      </span>
    )
  }
  return <span style={{ whiteSpace: 'pre-wrap' }}>{String(value)}</span>
}

/**
 * Dynamic fill/edit form rendered from a template format. Submits the
 * answers object (nulls for untouched optional questions). The form
 * instance is owned by the parent so server-side per-field errors can be
 * fed back into it; validation is explicit (Persian per-field messages),
 * NOT the silent min/max clamping of InputNumber.
 */
export function QuestionnaireForm({
  format,
  initialAnswers,
  submitting,
  onFinish,
  form,
}: {
  format: FormatDoc
  initialAnswers?: Answers
  submitting?: boolean
  onFinish: (answers: Answers) => void
  form: FormInstance<Record<string, unknown>>
}) {
  const { token: themeToken } = theme.useToken()
  // the form store outlives this component (parent-owned instance) — reset
  // whenever the format or the seeded answers change so stale values/errors
  // never leak across responses
  const fmtKey = (format.questions ?? []).map((q) => q.key).join('|')
  useEffect(() => {
    form.resetFields()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form, fmtKey, initialAnswers])

  const finish = (values: Record<string, unknown>) => {
    // only include keys the user touched with a value; untouched stay absent
    const out: Answers = {}
    for (const q of format.questions ?? []) {
      const v = values[q.key]
      out[q.key] = (v === undefined || v === '' ? null : v) as never
    }
    onFinish(out)
  }

  return (
    <Form form={form} layout="vertical" onFinish={finish} initialValues={initialAnswers ?? {}}>
      {(format.questions ?? []).map((q) => (
        <Form.Item
          key={q.key}
          name={q.key}
          label={
            <span>
              {q.label}
              {q.required && <span style={{ color: themeToken.colorError }}> *</span>}
            </span>
          }
          rules={questionRule(q)}
        >
          {q.type === 'number' ? (
            <InputNumber
              style={{ width: 200 }}
              parser={(v) => toEnDigits(v ?? '')}
              addonAfter={q.unit || undefined}
              suffix={
                rangeHint(q) ? (
                  <span style={{ color: themeToken.colorTextSecondary, fontSize: 11, direction: 'ltr' }}>
                    {rangeHint(q)}
                  </span>
                ) : undefined
              }
            />
          ) : q.type === 'choice' ? (
            <Radio.Group>
              <Space direction="vertical" size={2}>
                {q.options.map((o) => (
                  <Radio key={o.value} value={o.value}>
                    {o.label}
                    {typeof o.score === 'number' && (
                      <Typography.Text type="secondary" style={{ fontSize: 11, marginInlineStart: 6 }}>
                        ({o.score})
                      </Typography.Text>
                    )}
                  </Radio>
                ))}
              </Space>
            </Radio.Group>
          ) : q.multiline ? (
            <Input.TextArea rows={3} maxLength={q.max_length} />
          ) : (
            <Input maxLength={q.max_length} />
          )}
        </Form.Item>
      ))}
      <Button type="primary" htmlType="submit" loading={submitting}>
        ذخیره
      </Button>
    </Form>
  )
}
