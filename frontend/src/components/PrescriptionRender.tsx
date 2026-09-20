import { useEffect, useRef, useState } from 'react'
import {
  App as AntApp,
  AutoComplete,
  Button,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Space,
  Tag,
  Typography,
  type FormInstance,
} from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'

import { api, apiError } from '../api/client'
import type { NamedRef, Prescription, PrescriptionItemInput } from '../api/types'
import { formatJalali, formatJalaliTime, toFaDigits } from '../lib/jalali'
import { JalaliDateTimePicker } from './JalaliDates'

/** One editable row of the prescription form. */
export interface PrescriptionRow {
  name: string
  quantity?: number | null
}

/** Form payload produced by PrescriptionForm.onFinish. */
export interface PrescriptionFormValues {
  prescribed_at?: string
  notes: string
  items: PrescriptionRow[]
}

/**
 * Read-only rendering of one prescription: items as «name × qty» chips
 * (missing quantity renders as just the name), notes, date + author.
 */
export function PrescriptionView({ rx, onEdit }: { rx: Prescription; onEdit?: () => void }) {
  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      {onEdit && (
        <div>
          <Button size="small" icon={<EditOutlined />} onClick={onEdit}>
            ویرایش نسخه
          </Button>
        </div>
      )}
      <Descriptions bordered column={1} size="small">
        <Descriptions.Item label="اقلام">
          {rx.items.length === 0 ? (
            <Typography.Text type="secondary">—</Typography.Text>
          ) : (
            <Space wrap size={4}>
              {rx.items.map((it) => (
                <Tag key={it.id} color="geekblue" style={{ marginInlineEnd: 0 }}>
                  {it.quantity != null
                    ? `${it.item_name} × ${toFaDigits(String(it.quantity))}`
                    : it.item_name}
                </Tag>
              ))}
            </Space>
          )}
        </Descriptions.Item>
        <Descriptions.Item label="زمان تجویز">
          {formatJalali(rx.prescribed_at)} — ساعت {formatJalaliTime(rx.prescribed_at)}
        </Descriptions.Item>
        <Descriptions.Item label="تجویزکننده">
          {rx.created_by_username ?? '—'}
          {rx.source_appointment_id != null && (
            <Typography.Text type="secondary" style={{ marginInlineStart: 8, fontSize: 12 }}>
              (تبدیل‌شده از نسخه متنی نوبت شماره {toFaDigits(String(rx.source_appointment_id))})
            </Typography.Text>
          )}
        </Descriptions.Item>
        <Descriptions.Item label="یادداشت">
          {rx.notes ? (
            <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
              {rx.notes}
            </Typography.Paragraph>
          ) : (
            <Typography.Text type="secondary">—</Typography.Text>
          )}
        </Descriptions.Item>
      </Descriptions>
    </Space>
  )
}

/**
 * Prescription editor: type an item name → suggestions from the clinic
 * dictionary (server search); a new name is auto-registered on save.
 * Quantity is per item and optional. The form instance is parent-owned
 * (unsaved-changes guard watches it from outside); `seed` (applied after
 * every reset — the instance outlives the component) gives the parent
 * control over the freshly-opened state, e.g. one empty row for create.
 */
export function PrescriptionForm({
  form,
  initial,
  seed,
  submitting,
  onFinish,
}: {
  form: FormInstance<PrescriptionFormValues>
  initial?: Prescription
  seed?: PrescriptionFormValues
  submitting?: boolean
  onFinish: (values: {
    prescribed_at?: string
    notes: string
    items: PrescriptionItemInput[]
  }) => void
}) {
  const { message } = AntApp.useApp()
  // server dictionary lookups: name (lower) → id — lets us send item_id for
  // known names and a bare name for new ones (the API dedupes case-
  // insensitively; unknown names are auto-registered)
  const knownIds = useRef<Map<string, number>>(new Map())
  const [suggestions, setSuggestions] = useState<NamedRef[]>([])
  const [searching, setSearching] = useState(false)

  useEffect(() => {
    form.resetFields() // back to the initialValues prop (built from `initial`)
    if (seed) form.setFieldsValue(seed) // then the parent's fresh-open state
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form, initial, seed])

  const searchItems = async (q: string) => {
    const text = q.trim()
    if (!text) {
      setSuggestions([])
      return
    }
    setSearching(true)
    try {
      const page = (
        await api.get<{ items: NamedRef[] }>('/prescription-items', {
          params: { q: text, limit: 20 },
        })
      ).data
      for (const it of page.items) knownIds.current.set(it.name.toLowerCase(), it.id)
      setSuggestions(page.items)
    } catch (err) {
      message.error(apiError(err).message)
    } finally {
      setSearching(false)
    }
  }

  const finish = (values: PrescriptionFormValues) => {
    const items: PrescriptionItemInput[] = (values.items ?? []).map((row) => {
      const id = knownIds.current.get((row.name ?? '').trim().toLowerCase())
      return {
        item_id: id,
        name: id === undefined ? (row.name ?? '').trim() : undefined,
        quantity: row.quantity == null ? null : Number(row.quantity),
      }
    })
    onFinish({ prescribed_at: values.prescribed_at, notes: values.notes ?? '', items })
  }

  return (
    <Form
      form={form}
      layout="vertical"
      onFinish={finish}
      initialValues={{
        notes: initial?.notes ?? '',
        items: (initial?.items ?? []).map((it) => ({
          name: it.item_name,
          quantity: it.quantity,
        })),
      }}
    >
      <Form.Item name="prescribed_at" label="زمان تجویز">
        <JalaliDateTimePicker />
      </Form.Item>
      <Form.List name="items">
        {(fields, { add, remove }) => (
          <>
            {fields.map((field) => (
              <Space key={field.key} align="baseline" wrap>
                <Form.Item
                  name={[field.name, 'name']}
                  rules={[{ required: true, message: 'نام قلم الزامی است' }]}
                  style={{ minWidth: 280 }}
                >
                  <AutoComplete
                    placeholder="نام دارو/آزمایش (مثلاً P1)"
                    options={suggestions
                      .filter((s) => s.name !== form.getFieldValue(['items', field.name, 'name']))
                      .map((s) => ({ value: s.name }))}
                    onSearch={(text) => void searchItems(text)}
                    filterOption={false}
                    notFoundContent={searching ? '…' : undefined}
                  />
                </Form.Item>
                <Form.Item
                  name={[field.name, 'quantity']}
                  rules={[
                    {
                      type: 'integer',
                      min: 1,
                      message: 'تعداد باید عدد صحیح ≥ ۱ باشد (خالی = بدون تعداد)',
                    },
                  ]}
                >
                  <InputNumber placeholder="تعداد" style={{ width: 120 }} />
                </Form.Item>
                <Button
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => remove(field.name)}
                />
              </Space>
            ))}
            <Button type="dashed" onClick={() => add({ name: '' })} icon={<PlusOutlined />} block>
              افزودن قلم
            </Button>
          </>
        )}
      </Form.List>
      <Form.Item name="notes" label="یادداشت" style={{ marginTop: 16 }}>
        <Input.TextArea rows={2} maxLength={10000} placeholder="اختیاری" />
      </Form.Item>
      <Button type="primary" htmlType="submit" loading={submitting}>
        ذخیره
      </Button>
    </Form>
  )
}
