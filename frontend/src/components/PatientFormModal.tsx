import { useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App as AntApp, Form, Input, Modal, Select } from 'antd'

import { api, apiError } from '../api/client'
import type { NamedRef, Page, Patient } from '../api/types'

export interface PatientForm {
  national_id: string
  first_name: string
  last_name: string
  insurance?: string
  year_of_birth: string
  phone_number?: string
  gender: 0 | 1
  tag_ids?: number[]
  diagnosis_ids?: number[]
}

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
  const qc = useQueryClient()
  const [form] = Form.useForm<PatientForm>()

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
      if (patient) {
        return (
          await api.patch<Patient>(`/patients/${patient.id}`, values)
        ).data
      }
      return (await api.post<Patient>('/patients', values)).data
    },
    onSuccess: (saved) => {
      message.success('ذخیره شد')
      qc.invalidateQueries({ queryKey: ['patients'] })
      qc.invalidateQueries({ queryKey: ['patient'] })
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
          <Input />
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
          <Input />
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
          <Input />
        </Form.Item>
        <Form.Item name="insurance" label="بیمه">
          <Input />
        </Form.Item>
        <Form.Item name="tag_ids" label="برچسب‌ها">
          <Select
            mode="multiple"
            showSearch
            optionFilterProp="label"
            options={(tags.data ?? []).map((t) => ({ value: t.id, label: t.name }))}
          />
        </Form.Item>
        <Form.Item name="diagnosis_ids" label="تشخیص‌ها">
          <Select
            mode="multiple"
            showSearch
            optionFilterProp="label"
            options={(diagnoses.data ?? []).map((d) => ({ value: d.id, label: d.name }))}
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}
