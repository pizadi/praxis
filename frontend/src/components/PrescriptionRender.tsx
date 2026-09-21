import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
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
import { DeleteOutlined, EditOutlined } from '@ant-design/icons'

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
    // trailing-empty-row invariant must hold in EDIT mode too (create gets
    // it via seed): without an empty row to type into, a new item cannot be
    // added at all (there is no add button)
    const rows: PrescriptionRow[] = form.getFieldValue('items') ?? []
    const last = rows[rows.length - 1]
    const lastEmpty =
      last != null &&
      String(last.name ?? '').trim() === '' &&
      String(last.quantity ?? '').trim() === ''
    if (!lastEmpty) {
      form.setFieldValue('items', [...rows, { name: '', quantity: null }])
    }
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
    const items: PrescriptionItemInput[] = []
    for (const row of values.items ?? []) {
      const name = (row.name ?? '').trim()
      const qtyStr = row.quantity == null ? '' : String(row.quantity).trim()
      const qty = qtyStr === '' ? null : Number(qtyStr)
      if (!name && qtyStr === '') continue // an abandoned empty row — drop silently
      if (!name) {
        message.error('برای قلمی که تعداد دارد، نام را وارد کنید')
        return
      }
      const id = knownIds.current.get(name.toLowerCase())
      items.push({
        item_id: id,
        name: id === undefined ? name : undefined,
        quantity: qty,
      })
    }
    onFinish({ prescribed_at: values.prescribed_at, notes: values.notes ?? '', items })
  }

  // Enter must never submit the form (a half-typed row is not a save
  // intention). Block the browser's implicit submit for every input except
  // textareas (newlines are legitimate there) and buttons (keyboard
  // activation of ذخیره must keep working).
  const blockSubmitEnter = (e: KeyboardEvent) => {
    const t = e.target as HTMLElement
    if (e.key !== 'Enter' || t.tagName === 'TEXTAREA' || t.tagName === 'BUTTON') return
    e.preventDefault()
  }

  return (
    <Form
      form={form}
      layout="vertical"
      onKeyDown={blockSubmitEnter}
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
        {(fields, { add, remove }) => {
          // trailing-empty-row invariant: the list always ends with one
          // empty row — typing in it spawns another row underneath; a row
          // left completely empty is dropped when it loses focus (unless it
          // IS the trailing affordance row)
          const isLast = (idx: number) => idx === fields.length - 1
          const appendIfLast = (idx: number, value: unknown) => {
            const filled = typeof value === 'string' ? value.trim() !== '' : value != null
            if (isLast(idx) && filled) add({ name: '' })
          }
          const dropIfAbandoned = (idx: number) => {
            const list: PrescriptionRow[] = form.getFieldValue('items') ?? []
            const row = list[idx]
            const name = String(row?.name ?? '').trim()
            const qtyStr = row?.quantity == null ? '' : String(row.quantity).trim()
            if (name === '' && qtyStr === '' && !isLast(idx)) remove(idx)
          }
          return (
            <>
              {fields.map((field) => (
                <Space key={field.key} align="baseline" wrap>
                  <Form.Item
                    name={[field.name, 'name']}
                    style={{ minWidth: 280 }}
                  >
                    <AutoComplete
                      placeholder="نام دارو/آزمایش (مثلاً P1)"
                      options={suggestions
                        .filter((s) => s.name !== form.getFieldValue(['items', field.name, 'name']))
                        .map((s) => ({ value: s.name }))}
                      onSearch={(text) => void searchItems(text)}
                      onChange={(v) => appendIfLast(field.name, v)}
                      onBlur={() => dropIfAbandoned(field.name)}
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
                    <InputNumber
                      placeholder="تعداد"
                      style={{ width: 120 }}
                      onChange={(v) => appendIfLast(field.name, v)}
                      onBlur={() => dropIfAbandoned(field.name)}
                    />
                  </Form.Item>
                  <Button
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => {
                      remove(field.name)
                      if (fields.length <= 1) add({ name: '' }) // keep the affordance row
                    }}
                  />
                </Space>
              ))}
            </>
          )
        }}
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
