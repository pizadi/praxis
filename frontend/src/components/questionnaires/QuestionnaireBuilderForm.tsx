import { Fragment, useEffect, useMemo, useState } from 'react'
import {
  Button,
  Card,
  Divider,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Tabs,
  Typography,
  theme,
} from 'antd'
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons'

import { api, apiError } from '../../api/client'
import type { FormatDoc } from '../../lib/questionnaire'
import { faFormulaError } from '../../lib/questionnaire'

export interface BuilderQuestion {
  key: string
  label: string
  type: 'number' | 'choice' | 'string'
  required: boolean
  // number
  min?: number
  max?: number
  integer?: boolean
  unit?: string
  // choice
  options?: { value: string; label: string; score?: number }[]
  // string
  multiline?: boolean
  max_length?: number
}

export interface BuilderState {
  name: string
  description: string
  title: string
  questions: BuilderQuestion[]
  score_formula?: string
}

export function builderToFormat(values: BuilderState): FormatDoc {
  return {
    version: 1,
    title: values.title ?? '',
    score_formula: (values.score_formula ?? '').trim(),
    questions: (values.questions ?? []).map((question) => {
      const base = {
        key: question.key,
        label: question.label,
        type: question.type,
        required: !!question.required,
      }
      if (question.type === 'number') {
        return {
          ...base,
          type: 'number' as const,
          min: question.min ?? null,
          max: question.max ?? null,
          integer: !!question.integer,
          unit: question.unit ?? '',
        }
      }
      if (question.type === 'choice') {
        return {
          ...base,
          type: 'choice' as const,
          options: (question.options ?? []).map((option) => ({
            value: option.value,
            label: option.label,
            score: option.score ?? null,
          })),
        }
      }
      return {
        ...base,
        type: 'string' as const,
        multiline: !!question.multiline,
        max_length: question.max_length ?? 10000,
      }
    }),
  }
}

export function formatToBuilder(format: FormatDoc, name = '', description = '') {
  return {
    name,
    description,
    title: format.title ?? '',
    score_formula: format.score_formula ?? '',
    questions: (format.questions ?? []).map(
      (question) => ({ ...question }),
    ) as BuilderQuestion[],
  }
}

/** The graphical template builder plus its JSON preview. */
export default function QuestionnaireBuilderForm({
  form,
  onFinish,
}: {
  form: ReturnType<typeof Form.useForm<BuilderState>>[0]
  onFinish: (values: BuilderState) => void
}) {
  const { token: themeToken } = theme.useToken()
  const [tab, setTab] = useState<'builder' | 'json'>('builder')
  const values = Form.useWatch([], form)
  const scorableKeys = (values?.questions ?? [])
    .filter((question) => question.type === 'number' || question.type === 'choice')
    .map((question) => question.key)
    .filter(Boolean)
  const [formulaError, setFormulaError] = useState<string | null>(null)
  const preview = useMemo(() => {
    try {
      if (!values?.questions?.length) return null
      return JSON.stringify(builderToFormat(values), null, 2)
    } catch {
      return null
    }
  }, [values])

  // The server owns formula validation; the client renders its authoritative
  // result after a short debounce so typing does not create a request per key.
  useEffect(() => {
    const text = (values?.score_formula ?? '').trim()
    if (!text) {
      setFormulaError(null)
      return
    }
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      try {
        await api.post(
          '/questionnaires/formulas/validate',
          {
            score_formula: text,
            questions: (values?.questions ?? []).map((question) => ({
              key: question.key,
              type: question.type,
            })),
          },
          { signal: controller.signal },
        )
        setFormulaError(null)
      } catch (error) {
        if (controller.signal.aborted) return
        setFormulaError(faFormulaError(apiError(error).message))
      }
    }, 300)
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [values?.score_formula, values?.questions])

  return (
    <Tabs
      activeKey={tab}
      onChange={(key) => setTab(key as 'builder' | 'json')}
      items={[
        {
          key: 'builder',
          label: 'ساختگر گرافیکی',
          children: (
            <Form form={form} layout="vertical" onFinish={onFinish}>
              <Space size="middle" style={{ display: 'flex' }}>
                <Form.Item
                  name="name"
                  label="نام قالب"
                  rules={[{ required: true, message: 'نام الزامی است' }]}
                >
                  <Input maxLength={128} style={{ width: 240 }} />
                </Form.Item>
                <Form.Item name="description" label="توضیح">
                  <Input maxLength={512} style={{ width: 300 }} />
                </Form.Item>
              </Space>
              <Form.Item name="title" label="عنوان پرسش‌نامه">
                <Input maxLength={256} />
              </Form.Item>

              <Typography.Text strong>پرسش‌ها</Typography.Text>
              <Form.List name="questions">
                {(fields, { add, remove }) => (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {fields.map((field) => (
                      <Fragment key={field.key}>
                        <div className="q-gap">
                          <Button
                            type="text"
                            shape="circle"
                            size="small"
                            icon={<PlusOutlined />}
                            title="درج پرسش اینجا"
                            aria-label="درج پرسش اینجا"
                            onClick={() =>
                              add(
                                { key: '', label: '', type: 'string', required: false },
                                field.name,
                              )
                            }
                          />
                        </div>
                        <Card size="small" styles={{ body: { paddingTop: 12 } }}>
                          <Space align="baseline" wrap>
                            <Form.Item
                              name={[field.name, 'key']}
                              label="کلید"
                              rules={[
                                { required: true, message: 'کلید الزامی است' },
                                {
                                  pattern: /^[a-z0-9_]{1,64}$/,
                                  message: 'فقط حروف کوچک انگلیسی، رقم و _',
                                },
                              ]}
                            >
                              <Input style={{ width: 150 }} placeholder="pain_level" />
                            </Form.Item>
                            <Form.Item
                              name={[field.name, 'label']}
                              label="متن پرسش"
                              rules={[{ required: true, message: 'متن الزامی است' }]}
                            >
                              <Input style={{ width: 220 }} />
                            </Form.Item>
                            <Form.Item
                              name={[field.name, 'type']}
                              label="نوع"
                              initialValue="string"
                            >
                              <Select
                                style={{ width: 120 }}
                                options={[
                                  { value: 'number', label: 'عدد' },
                                  { value: 'choice', label: 'چندگزینه‌ای' },
                                  { value: 'string', label: 'متنی' },
                                ]}
                              />
                            </Form.Item>
                            <Form.Item
                              name={[field.name, 'required']}
                              label="الزامی"
                              valuePropName="checked"
                              initialValue={false}
                            >
                              <Switch />
                            </Form.Item>
                            <Button
                              type="text"
                              danger
                              icon={<MinusCircleOutlined />}
                              onClick={() => remove(field.name)}
                            />
                          </Space>

                          <TypeSpecificFields form={form} field={field.name} />
                        </Card>
                      </Fragment>
                    ))}
                    <Button
                      type="dashed"
                      icon={<PlusOutlined />}
                      onClick={() => add({ key: '', label: '', type: 'string', required: false })}
                      style={{ width: 200 }}
                    >
                      پرسش جدید
                    </Button>
                  </div>
                )}
              </Form.List>

              <Divider style={{ margin: '16px 0 8px' }} />
              <Form.Item
                name="score_formula"
                label="فرمول جمع نمره (اختیاری)"
                validateStatus={formulaError ? 'error' : undefined}
                help={formulaError}
                extra={
                  `کلیدهای قابل استفاده: ${scorableKeys.join(', ') || '—'} — ` +
                  'عملگرها: + - * / و پرانتز؛ توابع: min، max، abs — پاسخ خالی نمره را باطل می‌کند'
                }
              >
                <Input
                  dir="ltr"
                  placeholder="مثلاً: 0.5 * pain_level + mobility"
                  style={{
                    width: '100%',
                    maxWidth: 420,
                    display: 'block',
                    direction: 'ltr',
                    textAlign: 'left',
                    fontFamily: 'monospace',
                  }}
                />
              </Form.Item>
            </Form>
          ),
        },
        {
          key: 'json',
          label: 'پیش‌نمایش JSON',
          children: (
            <>
              <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
                این JSON به‌صورت خودکار از ساختگر تولید می‌شود و در ذخیره‌سازی اعتبارسنجی خواهد شد.
              </Typography.Paragraph>
              <pre
                dir="ltr"
                style={{
                  background: themeToken.colorFillQuaternary,
                  padding: 12,
                  borderRadius: 8,
                  maxHeight: 380,
                  overflow: 'auto',
                  fontSize: 12,
                }}
              >
                {preview ?? '—'}
              </pre>
            </>
          ),
        },
      ]}
    />
  )
}

/** Type-specific controls, keyed off the current row's type value. */
function TypeSpecificFields({
  form,
  field,
}: {
  form: ReturnType<typeof Form.useForm<BuilderState>>[0]
  field: number
}) {
  const questionType = Form.useWatch(['questions', field, 'type'], form)
  if (questionType === 'number') {
    // cross-field check both ways: revalidates when the sibling changes
    const rangeRule = (
      sibling: 'min' | 'max',
      bad: (value: number, other: number) => boolean,
      message: string,
    ) => ({
      validator: (_rule: unknown, value: number | null | undefined) => {
        const other = form.getFieldValue(['questions', field, sibling])
        if (value != null && other != null && bad(value, other)) {
          return Promise.reject(new Error(message))
        }
        return Promise.resolve()
      },
    })
    return (
      <Space align="baseline" wrap style={{ marginTop: 0 }}>
        <Form.Item
          name={[field, 'min']}
          label="حداقل"
          dependencies={[['questions', field, 'max']]}
          rules={[rangeRule('max', (value, other) => value > other, 'حداقل باید ≤ حداکثر باشد')]}
        >
          <InputNumber style={{ width: 110 }} />
        </Form.Item>
        <Form.Item
          name={[field, 'max']}
          label="حداکثر"
          dependencies={[['questions', field, 'min']]}
          rules={[rangeRule('min', (value, other) => value < other, 'حداکثر باید ≥ حداقل باشد')]}
        >
          <InputNumber style={{ width: 110 }} />
        </Form.Item>
        <Form.Item name={[field, 'integer']} label="عدد صحیح" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item name={[field, 'unit']} label="واحد">
          <Input style={{ width: 90 }} maxLength={32} />
        </Form.Item>
      </Space>
    )
  }
  if (questionType === 'choice') {
    return (
      <div style={{ marginTop: 4 }}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          گزینه‌ها (نمره اختیاری برای گزینه‌های نمره‌دار)
        </Typography.Text>
        <Form.List name={[field, 'options']}>
          {(options, { add: addOption, remove: removeOption }) => (
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              {options.map((option) => (
                <Space key={option.key} align="baseline">
                  <Form.Item name={[option.name, 'value']} noStyle>
                    <Input placeholder="value (انگلیسی)" style={{ width: 140 }} />
                  </Form.Item>
                  <Form.Item name={[option.name, 'label']} noStyle>
                    <Input placeholder="برچسب" style={{ width: 160 }} />
                  </Form.Item>
                  <Form.Item name={[option.name, 'score']} noStyle>
                    <InputNumber placeholder="نمره" style={{ width: 90 }} />
                  </Form.Item>
                  <Button
                    type="text"
                    danger
                    size="small"
                    icon={<MinusCircleOutlined />}
                    onClick={() => removeOption(option.name)}
                  />
                </Space>
              ))}
              <Button
                size="small"
                icon={<PlusOutlined />}
                onClick={() => addOption({ value: '', label: '' })}
              >
                گزینه
              </Button>
            </Space>
          )}
        </Form.List>
      </div>
    )
  }
  if (questionType === 'string') {
    return (
      <Space align="baseline" wrap style={{ marginTop: 0 }}>
        <Form.Item name={[field, 'multiline']} label="چندخطی" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item name={[field, 'max_length']} label="حداکثر طول">
          <InputNumber style={{ width: 110 }} min={1} max={10000} />
        </Form.Item>
      </Space>
    )
  }
  return <Divider style={{ margin: '4px 0' }} />
}
