import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App as AntApp, Form, Input, Modal, Select } from 'antd'
import { PlusOutlined } from '@ant-design/icons'

import { api, apiError } from '../api/client'
import DigitInput from './DigitInput'
import { useUser } from './AppLayout'
import type { NamedRef, Page, Patient } from '../api/types'

export interface PatientForm {
  national_id: string
  first_name: string
  last_name: string
  insurance?: string
  year_of_birth: string
  phone_number?: string
  gender: 0 | 1
  /** numbers = existing ids; `__new__:…` strings = not-yet-created entries
   * (created server-side right before the patient form is submitted). */
  tag_ids?: (number | string)[]
  diagnosis_ids?: (number | string)[]
}

type TaxonomyKind = 'tags' | 'diagnoses'

const SENTINEL = '__new__:'

const sentinelText = (v: string) => v.slice(SENTINEL.length).split(':')[1]

/**
 * Create/edit patient modal. Pass `patient` to edit, nothing to create.
 * `onDone` fires after a successful save (used for redirects/invalidations).
 */
export default function PatientFormModal({
  open,
  patient,
  onCancel,
  onDone,
}: {
  open: boolean
  patient: Patient | null
  onCancel: () => void
  onDone: (saved: Patient) => void
}) {
  const { message } = AntApp.useApp()
  const { hasPerm } = useUser()
  const qc = useQueryClient()
  const [form] = Form.useForm<PatientForm>()
  const canWriteTax = hasPerm('taxonomies.write')

  const tags = useQuery({
    queryKey: ['tags'],
    queryFn: async () =>
      (await api.get<Page<NamedRef>>('/tags', { params: { limit: 1000 } })).data.items,
  })
  const diagnoses = useQuery({
    queryKey: ['diagnoses'],
    queryFn: async () =>
      (await api.get<Page<NamedRef>>('/diagnoses', { params: { limit: 1000 } })).data.items,
  })

  useEffect(() => {
    if (!open) return
    if (patient) {
      form.setFieldsValue({
        national_id: patient.national_id,
        first_name: patient.first_name,
        last_name: patient.last_name,
        insurance: patient.insurance ?? undefined,
        year_of_birth: patient.year_of_birth,
        phone_number: patient.phone_number,
        gender: patient.gender === 0 ? 0 : 1,
        tag_ids: patient.tags.map((t) => t.id),
        diagnosis_ids: patient.diagnoses.map((d) => d.id),
      })
    } else {
      form.resetFields()
    }
  }, [open, patient, form])

  const save = useMutation({
    mutationFn: async (values: PatientForm) => {
      // create not-yet-existing tags/diagnoses first, then submit the patient
      // form with real ids
      const tag_ids = await resolveTaxonomy('tags', values.tag_ids ?? [])
      const diagnosis_ids = await resolveTaxonomy('diagnoses', values.diagnosis_ids ?? [])
      const payload: PatientForm = { ...values, tag_ids, diagnosis_ids }
      if (patient) {
        return (await api.patch<Patient>(`/patients/${patient.id}`, payload)).data
      }
      return (await api.post<Patient>('/patients', payload)).data
    },
    onSuccess: (saved) => {
      message.success('ذخیره شد')
      qc.invalidateQueries({ queryKey: ['patients'] })
      qc.invalidateQueries({ queryKey: ['patient'] })
      qc.invalidateQueries({ queryKey: ['tags'] })
      qc.invalidateQueries({ queryKey: ['diagnoses'] })
      onDone(saved)
    },
    onError: (err) => message.error(apiError(err).message),
  })

  return (
    <Modal
      open={open}
      title={patient ? 'ویرایش بیمار' : 'بیمار جدید'}
      maskClosable={false}
      onCancel={onCancel}
      onOk={() => form.submit()}
      confirmLoading={save.isPending}
      destroyOnHidden
    >
      <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
        <Form.Item
          name="national_id"
          label="کد ملی"
          rules={[
            { required: true },
            { pattern: /^\d{10}$/, message: 'کد ملی باید ۱۰ رقم باشد' },
          ]}
        >
          <DigitInput inputMode="numeric" />
        </Form.Item>
        <Form.Item name="first_name" label="نام" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="last_name" label="نام خانوادگی" rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item
          name="year_of_birth"
          label="سال تولد"
          rules={[
            { required: true },
            { pattern: /^\d{4}$/, message: 'سال تولد باید ۴ رقم باشد' },
          ]}
        >
          <DigitInput inputMode="numeric" />
        </Form.Item>
        <Form.Item name="gender" label="جنسیت" rules={[{ required: true }]}>
          <Select
            options={[
              { value: 0, label: 'مرد' },
              { value: 1, label: 'زن' },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="phone_number"
          label="تلفن"
          rules={[{ pattern: /^\d+$/, message: 'فقط رقم' }]}
        >
          <DigitInput inputMode="tel" />
        </Form.Item>
        <Form.Item name="insurance" label="بیمه">
          <Input />
        </Form.Item>
        <TaxonomySelect
          name="tag_ids"
          label="برچسب‌ها"
          kind="tags"
          list={tags.data ?? []}
          canCreate={canWriteTax}
        />
        <TaxonomySelect
          name="diagnosis_ids"
          label="تشخیص‌ها"
          kind="diagnoses"
          list={diagnoses.data ?? []}
          canCreate={canWriteTax}
        />
      </Form>
    </Modal>
  )
}

/** Multi-select over an existing taxonomy with an inline «افزودن «…»»
 * option (perm-gated): typing a name that matches nothing offers creating
 * it; the sentinel is resolved to a real id right before the patient form
 * is submitted. */
function TaxonomySelect({
  name,
  label,
  kind,
  list,
  canCreate,
}: {
  name: 'tag_ids' | 'diagnosis_ids'
  label: string
  kind: TaxonomyKind
  list: NamedRef[]
  canCreate: boolean
}) {
  const form = Form.useFormInstance<PatientForm>()
  const selected: (number | string)[] | undefined = Form.useWatch(name, form)
  const [search, setSearch] = useState('')

  const options = useMemo(() => {
    const sel: (number | string)[] = selected ?? []
    const out: { value: number | string; label: ReactNode }[] = list.map((t) => ({
      value: t.id,
      label: t.name,
    }))
    // chips for selected not-yet-created entries render as the typed text
    for (const v of sel) {
      if (typeof v === 'string' && v.startsWith(SENTINEL)) {
        out.push({ value: v, label: sentinelText(v) })
      }
    }
    const text = search.trim()
    if (
      canCreate &&
      text &&
      !out.some((o) => typeof o.label === 'string' && o.label.toLowerCase().includes(text.toLowerCase())) &&
      !sel.includes(`__new__:${kind}:${text}`)
    ) {
      out.push({
        value: `__new__:${kind}:${text}`,
        label: (
          <span>
            <PlusOutlined /> افزودن «{text}»
          </span>
        ),
      })
    }
    return out
  }, [list, selected, canCreate, kind, search])

  return (
    <Form.Item name={name} label={label}>
      <Select
        mode="multiple"
        showSearch
        onSearch={(text) => setSearch(text)}
        onBlur={() => setSearch('')}
        options={options}
        filterOption={(input, option) => {
          // Sentinel values need custom filtering: the add-new option's
          // label is JSX (the default String(label) filter would hide it),
          // and already-selected sentinel chips must NOT reappear in the
          // dropdown while typing a different name (they would grab the
          // active option, so Enter would toggle them off instead of
          // adding the new tag). Only the add-new option for the current
          // search text passes.
          const v = option?.value
          if (typeof v === 'string' && v.startsWith(SENTINEL)) {
            return v === `__new__:${kind}:${input.trim()}`
          }
          return String(option?.label ?? '')
            .toLowerCase()
            .includes(input.toLowerCase())
        }}
      />
    </Form.Item>
  )
}

/** Create not-yet-existing tags/diagnoses; returns real ids in order.
 * A 409 `name_taken` (exact duplicate created meanwhile) falls back to the
 * existing entry instead of failing the save. */
async function resolveTaxonomy(kind: TaxonomyKind, values: (number | string)[]): Promise<number[]> {
  const out: number[] = []
  for (const v of values) {
    if (typeof v === 'number') {
      out.push(v)
      continue
    }
    const text = sentinelText(v)
    try {
      const created = (await api.post<NamedRef>(`/${kind}`, { name: text })).data
      out.push(created.id)
    } catch (err) {
      if (apiError(err).code === 'name_taken') {
        const found = (
          await api.get<Page<NamedRef>>(`/${kind}`, { params: { q: text, limit: 1000 } })
        ).data.items
        const hit =
          found.find((t) => t.name === text) ??
          found.find((t) => t.name.toLowerCase() === text.toLowerCase())
        if (hit) {
          out.push(hit.id)
          continue
        }
      }
      throw err
    }
  }
  return out
}
