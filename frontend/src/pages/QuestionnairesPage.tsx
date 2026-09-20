import { Fragment, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntApp,
  Button,
  Card,
  Divider,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Typography,
  Upload,
  theme,
} from 'antd'
import type { UploadFile } from 'antd'
import { CloudUploadOutlined, DeleteOutlined, DownloadOutlined, MinusCircleOutlined, PlusOutlined } from '@ant-design/icons'

import { api, apiError } from '../api/client'
import type { Page, QuestionnaireTemplate } from '../api/types'
import type { FormatDoc } from '../lib/questionnaire'
import { validateFormulaText } from '../lib/questionnaire'

/** Example JSON users can download as a starting point for uploads. */
const EXAMPLE_FORMAT: FormatDoc = {
  version: 1,
  title: 'پرسش‌نامه نمونه',
  // total score = arithmetic over question keys (number value / choice score)
  score_formula: 'pain_level + mobility',
  questions: [
    { key: 'pain', label: 'شدت درد (۰ تا ۱۰)', type: 'number', required: true, min: 0, max: 10, integer: true, unit: '' },
    {
      key: 'mobility',
      label: 'میزان تحرک',
      type: 'choice',
      required: false,
      options: [
        { value: 'bad', label: 'بد', score: 0 },
        { value: 'ok', label: 'متوسط', score: 1 },
        { value: 'good', label: 'خوب', score: 2 },
      ],
    },
    { key: 'notes', label: 'توضیحات', type: 'string', required: false, multiline: true, max_length: 500 },
  ],
}

interface BuilderQuestion {
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

interface BuilderState {
  name: string
  description: string
  title: string
  questions: BuilderQuestion[]
  score_formula?: string
}

export default function QuestionnairesPage() {
  const { message } = AntApp.useApp()
  const qc = useQueryClient()
  const [form] = Form.useForm<BuilderState>()
  const [editing, setEditing] = useState<QuestionnaireTemplate | null>(null)
  const [open, setOpen] = useState(false)
  const [uploadList, setUploadList] = useState<UploadFile[]>([])

  const templates = useQuery({
    queryKey: ['questionnaire-templates'],
    queryFn: async () =>
      (await api.get<Page<QuestionnaireTemplate>>('/questionnaires/templates', {
        params: { limit: 200 },
      })).data,
  })

  const save = useMutation({
    mutationFn: async (values: BuilderState) => {
      const fmt = builderToFormat(values)
      const body = { name: values.name, description: values.description, format: fmt }
      if (editing) return api.patch(`/questionnaires/templates/${editing.id}`, body)
      return api.post('/questionnaires/templates', body)
    },
    onSuccess: async () => {
      message.success('ذخیره شد')
      setOpen(false)
      setEditing(null)
      form.resetFields()
      setUploadList([])
      await qc.invalidateQueries({ queryKey: ['questionnaire-templates'] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const remove = useMutation({
    mutationFn: async (id: number) => api.delete(`/questionnaires/templates/${id}`),
    onSuccess: async () => {
      message.success('به سبد بازیافت منتقل شد')
      await qc.invalidateQueries({ queryKey: ['questionnaire-templates'] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  /** Upload a JSON file: parsed client-side, validated by the server
   * endpoint, then loaded into the graphical builder for review. */
  const loadFromJson = async (file: File) => {
    try {
      const text = await file.text()
      const parsed = JSON.parse(text) as Record<string, unknown>
      // server-side validation (same path as saving, minus the persist)
      const check = await api.post('/questionnaires/templates/validate', {
        name: (parsed.title as string) || file.name.replace(/\.json$/i, ''),
        description: '',
        format: parsed,
      })
      const fmt = check.data.format as FormatDoc
      const state = formatToBuilder(fmt)
      form.setFieldsValue({
        ...state,
        name: form.getFieldValue('name') || check.data.name,
      })
      setUploadList([])
      setEditing(null)
      setOpen(true)
      message.success('فایل معتبر است و در فرم بارگذاری شد — بررسی و ذخیره کنید')
    } catch (err) {
      message.error(apiError(err).message)
    }
    return false // prevent antd auto-upload
  }

  const openEdit = (t: QuestionnaireTemplate | null) => {
    setEditing(t)
    setUploadList([])
    if (t) {
      form.setFieldsValue(formatToBuilder(t.format as FormatDoc, t.name, t.description))
    } else {
      form.resetFields()
    }
    setOpen(true)
  }

  const downloadExample = () => {
    const blob = new Blob([JSON.stringify(EXAMPLE_FORMAT, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'questionnaire-example.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <Typography.Title level={3}>قالب‌های پرسش‌نامه</Typography.Title>
      <Card
        extra={
          <Space>
            <Button icon={<DownloadOutlined />} onClick={downloadExample}>
              نمونه JSON
            </Button>
            <Upload
              maxCount={1}
              accept=".json,application/json"
              fileList={uploadList}
              beforeUpload={(file) => loadFromJson(file)}
              onChange={({ fileList }) => setUploadList(fileList.slice(-1))}
            >
              <Button icon={<CloudUploadOutlined />}>بارگذاری JSON</Button>
            </Upload>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setEditing(null)
                form.resetFields()
                setOpen(true)
              }}
            >
              قالب جدید
            </Button>
          </Space>
        }
      >
        <Table<QuestionnaireTemplate>
          rowKey="id"
          loading={templates.isLoading}
          dataSource={templates.data?.items ?? []}
          pagination={false}
          columns={[
            { title: 'نام', dataIndex: 'name' },
            { title: 'توضیح', dataIndex: 'description' },
            {
              title: 'تعداد پرسش‌ها',
              render: (_, t) => (t.format?.questions ?? []).length,
            },
            {
              title: 'عملیات',
              render: (_, t) => (
                <Space>
                  <Button size="small" onClick={() => openEdit(t)}>
                    ویرایش
                  </Button>
                  <Popconfirm title="قالب به سبد بازیافت منتقل شود؟" onConfirm={() => remove.mutate(t.id)}>
                    <Button size="small" danger icon={<DeleteOutlined />} />
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        open={open}
        title={editing ? `ویرایش قالب: ${editing.name}` : 'قالب جدید'}
        maskClosable={false}
        onCancel={() => {
          setOpen(false)
          setEditing(null)
        }}
        onOk={() => form.submit()}
        confirmLoading={save.isPending}
        width={860}
        destroyOnHidden
      >
        <BuilderForm form={form} onFinish={(v) => save.mutate(v)} />
      </Modal>
    </div>
  )
}

// --- builder <-> format conversion -------------------------------------------

function builderToFormat(v: BuilderState): FormatDoc {
  return {
    version: 1,
    title: v.title ?? '',
    score_formula: (v.score_formula ?? '').trim(),
    questions: (v.questions ?? []).map((q) => {
      const base = { key: q.key, label: q.label, type: q.type, required: !!q.required }
      if (q.type === 'number') {
        return {
          ...base,
          type: 'number' as const,
          min: q.min ?? null,
          max: q.max ?? null,
          integer: !!q.integer,
          unit: q.unit ?? '',
        }
      }
      if (q.type === 'choice') {
        return {
          ...base,
          type: 'choice' as const,
          options: (q.options ?? []).map((o) => ({
            value: o.value,
            label: o.label,
            score: o.score ?? null,
          })),
        }
      }
      return {
        ...base,
        type: 'string' as const,
        multiline: !!q.multiline,
        max_length: q.max_length ?? 10000,
      }
    }),
  }
}

function formatToBuilder(fmt: FormatDoc, name = '', description = '') {
  return {
    name,
    description,
    title: fmt.title ?? '',
    score_formula: fmt.score_formula ?? '',
    questions: (fmt.questions ?? []).map((q) => ({ ...q })) as BuilderQuestion[],
  }
}

// --- the graphical builder ------------------------------------------------------

function BuilderForm({
  form,
  onFinish,
}: {
  form: ReturnType<typeof Form.useForm<BuilderState>>[0]
  onFinish: (v: BuilderState) => void
}) {
  const { token: themeToken } = theme.useToken()
  const [tab, setTab] = useState<'builder' | 'json'>('builder')
  const values = Form.useWatch([], form)
  const scorableKeys = (values?.questions ?? [])
    .filter((q) => q.type === 'number' || q.type === 'choice')
    .map((q) => q.key)
    .filter(Boolean)
  const preview = useMemo(() => {
    try {
      if (!values?.questions?.length) return null
      return JSON.stringify(builderToFormat(values), null, 2)
    } catch {
      return null
    }
  }, [values])

  return (
    <Tabs
      activeKey={tab}
      onChange={(k) => setTab(k as 'builder' | 'json')}
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
                          <Form.Item name={[field.name, 'type']} label="نوع" initialValue="string">
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
                extra={
                  `کلیدهای قابل استفاده: ${scorableKeys.join(', ') || '—'} — ` +
                  'عملگرها: + - * / و پرانتز؛ توابع: min، max، abs — پاسخ خالی نمره را باطل می‌کند'
                }
                rules={[
                  {
                    validator: (_rule, value: string) => {
                      const err = validateFormulaText(value ?? '', values?.questions ?? [])
                      return err ? Promise.reject(new Error(err)) : Promise.resolve()
                    },
                  },
                ]}
              >
                <Input
                  dir="ltr"
                  placeholder="مثلاً: 0.5 * pain_level + mobility"
                  style={{
                    width: 420,
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
function TypeSpecificFields({ form, field }: { form: ReturnType<typeof Form.useForm<BuilderState>>[0]; field: number }) {
  const qType = Form.useWatch(['questions', field, 'type'], form)
  if (qType === 'number') {
    // cross-field check both ways: revalidates when the sibling changes
    const rangeRule = (
      sibling: 'min' | 'max',
      bad: (v: number, other: number) => boolean,
      message: string,
    ) => ({
      validator: (_rule: unknown, v: number | null | undefined) => {
        const other = form.getFieldValue(['questions', field, sibling])
        if (v != null && other != null && bad(v, other)) {
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
          rules={[rangeRule('max', (v, o) => v > o, 'حداقل باید ≤ حداکثر باشد')]}
        >
          <InputNumber style={{ width: 110 }} />
        </Form.Item>
        <Form.Item
          name={[field, 'max']}
          label="حداکثر"
          dependencies={[['questions', field, 'min']]}
          rules={[rangeRule('min', (v, o) => v < o, 'حداکثر باید ≥ حداقل باشد')]}
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
  if (qType === 'choice') {
    return (
      <div style={{ marginTop: 4 }}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          گزینه‌ها (نمره اختیاری برای گزینه‌های نمره‌دار)
        </Typography.Text>
        <Form.List name={[field, 'options']}>
          {(opts, { add: addOpt, remove: removeOpt }) => (
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              {opts.map((opt) => (
                <Space key={opt.key} align="baseline">
                  <Form.Item name={[opt.name, 'value']} noStyle>
                    <Input placeholder="value (انگلیسی)" style={{ width: 140 }} />
                  </Form.Item>
                  <Form.Item name={[opt.name, 'label']} noStyle>
                    <Input placeholder="برچسب" style={{ width: 160 }} />
                  </Form.Item>
                  <Form.Item name={[opt.name, 'score']} noStyle>
                    <InputNumber placeholder="نمره" style={{ width: 90 }} />
                  </Form.Item>
                  <Button
                    type="text"
                    danger
                    size="small"
                    icon={<MinusCircleOutlined />}
                    onClick={() => removeOpt(opt.name)}
                  />
                </Space>
              ))}
              <Button size="small" icon={<PlusOutlined />} onClick={() => addOpt({ value: '', label: '' })}>
                گزینه
              </Button>
            </Space>
          )}
        </Form.List>
      </div>
    )
  }
  if (qType === 'string') {
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
