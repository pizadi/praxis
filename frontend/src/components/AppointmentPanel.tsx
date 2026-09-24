import { forwardRef, useEffect, useMemo, useImperativeHandle, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntApp,
  Button,
  Card,
  Collapse,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Col,
  Space,
  Table,
  Tabs,
  Typography,
} from 'antd'
import {
  DeleteOutlined,
  DownloadOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'

import { api, apiError } from '../api/client'
import type {
  Appointment,
  Attachment,
  Page,
  Prescription,
  QuestionnaireResponse,
  QuestionnaireTemplate,
} from '../api/types'
import { downloadAttachment } from '../lib/files'
import { formatJalali, formatJalaliTime, fileSize } from '../lib/jalali'
import { stageOf, tehranDay } from '../lib/stages'
import { useUser } from './AppLayout'
import AppointmentPayments from './appointments/AppointmentPayments'
import AppointmentStageHeader from './appointments/AppointmentStageHeader'
import {
  PrescriptionForm,
  PrescriptionView,
  type PrescriptionFormValues,
} from './PrescriptionRender'
import { QuestionnaireView } from './QuestionnaireRender'

/** Imperative handle for the unsaved-changes guard in the patient page. */
export interface AppointmentPanelHandle {
  isDirty: () => boolean
  /** Submit the notes form (result surfaces via onSaved / field errors). */
  save: () => void
  /** Reset the notes form back to the server values. */
  reset: () => void
}

/** Browser-local ISO with offset (same format JalaliDateTimePicker emits). */
function toLocalIso(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  const tz = -d.getTimezoneOffset()
  const sign = tz >= 0 ? '+' : '-'
  const abs = Math.abs(tz)
  return (
    `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}` +
    `T${p(d.getHours())}:${p(d.getMinutes())}:00${sign}${p(Math.floor(abs / 60))}:${p(abs % 60)}`
  )
}

interface Props {
  appointmentId: number
  /** Reports whether the notes form has unsaved edits. */
  onDirtyChange?: (dirty: boolean) => void
  /** Fires after a successful notes save (used to complete a guarded navigation). */
  onSaved?: () => void
  /** Fires when a notes save fails (guard hook cleanup in the parent). */
  onSaveFailed?: () => void
}

/**
 * Full detail view of one appointment: stage header, then notes, the three
 * same-day «این ویزیت» tabs (files / prescriptions / questionnaires the
 * patient has on this appointment's Tehran day) and payments. Files and
 * prescriptions belong to the PATIENT since 1.3 — the all-history views
 * live on the patient page. The legacy free-text rx shows read-only
 * (deprecated — prescriptions are structured rows now).
 */
const AppointmentPanel = forwardRef<AppointmentPanelHandle, Props>(function AppointmentPanel(
  { appointmentId, onDirtyChange, onSaved, onSaveFailed },
  ref,
) {
  const { hasPerm } = useUser()
  const { message } = AntApp.useApp()
  const qc = useQueryClient()
  const [, setSearchParams] = useSearchParams()

  const appt = useQuery({
    queryKey: ['appointment', appointmentId],
    queryFn: async () => (await api.get<Appointment>(`/appointments/${appointmentId}`)).data,
  })

  // --- same-day associated items (patient-level rows on the visit's
  // Tehran day); each endpoint enforces its own read permission
  const patientId = appt.data?.patient_id
  const visitDay = appt.data ? tehranDay(appt.data.scheduled_at) : undefined

  const canRx = hasPerm('prescriptions.read')
  const visitRx = useQuery({
    queryKey: ['visit-prescriptions', appointmentId, patientId, visitDay],
    queryFn: async () =>
      (await api.get<Page<Prescription>>(`/patients/${patientId}/prescriptions`, {
        params: { date: visitDay, limit: 100 },
      })).data,
    enabled: canRx && patientId != null && visitDay != null,
  })

  const canFiles = hasPerm('files.read')
  const visitFiles = useQuery({
    queryKey: ['visit-files', appointmentId, patientId, visitDay],
    queryFn: async () =>
      (await api.get<Attachment[]>(`/patients/${patientId}/files`, {
        params: { date: visitDay },
      })).data,
    enabled: canFiles && patientId != null && visitDay != null,
  })

  const canQ = hasPerm('questionnaires.read')
  const visitQ = useQuery({
    queryKey: ['visit-questionnaires', appointmentId, patientId, visitDay],
    queryFn: async () =>
      (await api.get<Page<QuestionnaireResponse>>(`/patients/${patientId}/questionnaires`, {
        params: { date: visitDay, limit: 100 },
      })).data,
    enabled: canQ && patientId != null && visitDay != null,
  })

  // formats for rendering the same-day responses (read-only merge view)
  const qTemplates = useQuery({
    queryKey: ['questionnaire-templates'],
    queryFn: async () =>
      (await api.get<Page<QuestionnaireTemplate>>('/questionnaires/templates', {
        params: { limit: 100 },
      })).data,
    enabled: canQ,
  })
  const templateById = useMemo(() => {
    const map = new Map<number, QuestionnaireTemplate>()
    for (const t of qTemplates.data?.items ?? []) map.set(t.id, t)
    return map
  }, [qTemplates.data])

  const [notesForm] = Form.useForm<Appointment>()

  // --- unsaved-changes guard (notes form vs server values) ---
  const canMedical = hasPerm('medical_notes.view')
  const notesValues = Form.useWatch([], notesForm)
  const notesDirty = useMemo(() => {
    if (!canMedical || !appt.data || !notesValues) return false
    const norm = (v: unknown) => (v == null ? '' : String(v))
    const a2 = appt.data
    return (
      norm(notesValues.notes) !== norm(a2.notes) ||
      norm(notesValues.cm) !== norm(a2.cm) ||
      norm(notesValues.hx) !== norm(a2.hx) ||
      norm(notesValues.px) !== norm(a2.px)
    )
  }, [canMedical, appt.data, notesValues])

  useEffect(() => {
    onDirtyChange?.(notesDirty)
    return () => onDirtyChange?.(false) // unmount/view switch → not dirty anymore
  }, [notesDirty, onDirtyChange])

  useImperativeHandle(ref, () => ({
    isDirty: () => notesDirty,
    save: () => notesForm.submit(),
    reset: () => notesForm.resetFields(),
  }))

  const saveNotes = useMutation({
    mutationFn: async (values: Partial<Appointment>) =>
      api.patch(`/appointments/${appointmentId}`, values),
    onSuccess: () => {
      message.success('ذخیره شد')
      qc.invalidateQueries({ queryKey: ['appointment', appointmentId] })
      onSaved?.()
    },
    onError: (err) => {
      message.error(apiError(err).message)
      onSaveFailed?.()
    },
  })

  // --- stage advance/regress (±1; regress asks for confirmation) ---
  const changeStage = useMutation({
    mutationFn: async (direction: 'advance' | 'regress') =>
      api.patch(`/appointments/${appointmentId}/stage`, { direction }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['appointment', appointmentId] })
      await qc.invalidateQueries({ queryKey: ['patient-appointments'] })
      await qc.invalidateQueries({ queryKey: ['schedule'] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const deleteAppt = useMutation({
    mutationFn: async () => api.delete(`/appointments/${appointmentId}`),
    onSuccess: async () => {
      message.success('نوبت به سبد بازیافت منتقل شد')
      setSearchParams({})
      await qc.invalidateQueries({ queryKey: ['patient-appointments'] })
      await qc.invalidateQueries({ queryKey: ['appointments'] })
      await qc.invalidateQueries({ queryKey: ['schedule'] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  // --- quick prescription add (patient-level; visit time pre-filled) ---
  const [rxModalOpen, setRxModalOpen] = useState(false)
  const [rxForm] = Form.useForm<PrescriptionFormValues>()
  const rxSeed: PrescriptionFormValues = useMemo(
    () => ({
      prescribed_at: toLocalIso(new Date(appt.data?.scheduled_at ?? Date.now())),
      notes: '',
      items: [{ name: '' }],
    }),
    [appt.data?.scheduled_at],
  )
  const addRx = useMutation({
    mutationFn: async (v: {
      prescribed_at?: string
      notes: string
      items: { item_id?: number; name?: string; quantity?: number | null }[]
    }) => api.post(`/patients/${patientId}/prescriptions`, v),
    onSuccess: () => {
      message.success('نسخه ثبت شد')
      setRxModalOpen(false)
      rxForm.resetFields()
      void qc.invalidateQueries({ queryKey: ['visit-prescriptions', appointmentId] })
      void qc.invalidateQueries({ queryKey: ['patient-prescriptions', patientId] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  if (appt.isLoading || !appt.data) {
    return <Card loading />
  }
  const a = appt.data
  const hasLegacyRx = a.rx.trim().length > 0
  const stage = stageOf(a.stage)

  const regressStageConfirm = () => {    Modal.confirm({
      title: `مرحله از «${stage.label}» به عقب برگردد؟`,
      content: 'این تغییر در گزارش اقدامات ثبت می‌شود.',
      okText: 'برگرداندن مرحله',
      cancelText: 'انصراف',
      maskClosable: false,
      onOk: () => changeStage.mutate('regress'),
    })
  }

  return (
    <>
      {/* stage header: current stage + advance/regress (regress prompted) */}
      <AppointmentStageHeader
        stage={a.stage}
        canChange={hasPerm('appointments.stage')}
        onAdvance={() => changeStage.mutate('advance')}
        onRegress={regressStageConfirm}
      />
      <Tabs
        tabBarExtraContent={
          hasPerm('appointments.delete') && (
            <Popconfirm
              title="نوبت به سبد بازیافت منتقل شود؟"
              onConfirm={() => deleteAppt.mutate()}
            >
              <Button size="small" danger icon={<DeleteOutlined />}>
                حذف نوبت
              </Button>
            </Popconfirm>
          )
        }
        items={[
        {
          key: 'notes',
          label: 'یادداشت‌ها',
          children: hasPerm('medical_notes.view') ? (
            <Form
              form={notesForm}
              layout="vertical"
              initialValues={{ notes: a.notes, cm: a.cm, hx: a.hx, px: a.px }}
              onFinish={(v) => saveNotes.mutate(v)}
            >
              <Form.Item name="notes" label="یادداشت">
                <Input.TextArea rows={2} />
              </Form.Item>
              <Row gutter={[12, 12]}>
                <Col xs={24} md={8}>
                  <Form.Item name="cm" label="CC / شرح حال فعلی">
                    <Input.TextArea rows={3} />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item name="hx" label="Hx — تاریخچه">
                    <Input.TextArea rows={3} />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item name="px" label="Px — معاینه">
                    <Input.TextArea rows={3} />
                  </Form.Item>
                </Col>
              </Row>
              <Button type="primary" htmlType="submit" loading={saveNotes.isPending}>
                ذخیره
              </Button>
              {hasLegacyRx && (
                <Collapse
                  size="small"
                  style={{ marginTop: 16 }}
                  items={[
                    {
                      key: 'legacy-rx',
                      label: 'نسخه قدیمی (متن آزاد — از سیستم قبلی)',
                      children: (
                        <Typography.Paragraph
                          style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}
                        >
                          {a.rx}
                        </Typography.Paragraph>
                      ),
                    },
                  ]}
                />
              )}
            </Form>
          ) : (
            <Typography.Text type="secondary">
              دسترسی پذیرش به یادداشت‌های پزشکی محدود است
            </Typography.Text>
          ),
        },
        {
          // same-day files (patient-level since 1.3) — all files on the patient page
          key: 'visit-files',
          label: 'فایل‌های این روز',
          children: !canFiles ? (
            <Typography.Text type="secondary">
              دسترسی مشاهده فایل‌ها را ندارید
            </Typography.Text>
          ) : (
            <Table<Attachment>
              rowKey="id"
              loading={visitFiles.isLoading}
              dataSource={visitFiles.data ?? []}
              pagination={false}
              size="small"
              locale={{ emptyText: 'فایلی در این روز ثبت نشده است' }}
              scroll={{ x: 'max-content' }}
              columns={[
                {
                  title: 'عنوان / شرح',
                  dataIndex: 'description',
                  render: (v: string, rec) => v || rec.original_filename || 'یادداشت',
                },
                { title: 'تاریخ', dataIndex: 'created_at', render: (v: string) => formatJalali(v) },
                {
                  title: 'ساعت',
                  dataIndex: 'created_at',
                  render: (v: string) => formatJalaliTime(v),
                },
                {
                  title: 'حجم',
                  dataIndex: 'size_bytes',
                  render: (v: number | null) => (v == null ? '—' : fileSize(v)),
                },
                {
                  title: '',
                  render: (_, rec) =>
                    rec.stored_filename ? (
                      <Button
                        size="small"
                        icon={<DownloadOutlined />}
                        onClick={() => downloadAttachment(rec.id, rec.original_filename)}
                      >
                        دانلود
                      </Button>
                    ) : null,
                },
              ]}
            />
          ),
        },
        {
          // same-day prescriptions (patient-level) — the all-history view
          // lives on the patient page
          key: 'visit-rx',
          label: 'نسخه‌های این روز',
          children: !canRx ? (
            <Typography.Text type="secondary">
              دسترسی مشاهده نسخه‌ها را ندارید
            </Typography.Text>
          ) : (
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              {hasPerm('prescriptions.write') && (
                <div>
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    onClick={() => setRxModalOpen(true)}
                  >
                    ثبت نسخه برای این بیمار
                  </Button>
                </div>
              )}
              {(visitRx.data?.items ?? []).length === 0 ? (
                <Typography.Text type="secondary">
                  در این روز نسخه‌ای ثبت نشده است
                </Typography.Text>
              ) : (
                (visitRx.data?.items ?? []).map((rx) => (
                  <Card key={rx.id} size="small">
                    <PrescriptionView rx={rx} />
                  </Card>
                ))
              )}
            </Space>
          ),
        },
        {
          // same-day questionnaire responses (patient-level)
          key: 'visit-q',
          label: 'پرسش‌نامه‌های این روز',
          children: !canQ ? (
            <Typography.Text type="secondary">
              دسترسی مشاهده پرسش‌نامه‌ها را ندارید
            </Typography.Text>
          ) : (
            (visitQ.data?.items ?? []).length === 0 ? (
              <Typography.Text type="secondary">
                در این روز پرسش‌نامه‌ای ثبت نشده است
              </Typography.Text>
            ) : (
              <Collapse
                size="small"
                items={(visitQ.data?.items ?? []).map((resp) => {
                  const tpl = templateById.get(resp.template_id)
                  return {
                    key: String(resp.id),
                    label: (
                      <Space size={8} wrap>
                        <Typography.Text strong>{resp.template_name}</Typography.Text>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {formatJalaliTime(resp.created_at)}
                          {resp.created_by_username ? ` — ${resp.created_by_username}` : ''}
                        </Typography.Text>
                      </Space>
                    ),
                    children: tpl ? (
                      <QuestionnaireView format={tpl.format} answers={resp.answers} />
                    ) : (
                      <Typography.Text type="warning">
                        قالب این پاسخ یافت نشد (قالب حذف شده است).
                      </Typography.Text>
                    ),
                  }
                })}
              />
            )
          ),
        },
        {
          key: 'txns',
          label: 'پرداخت‌ها',
          children: <AppointmentPayments appointmentId={appointmentId} />,
        },
      ]}
      />

      {/* quick-add prescription modal (patient-level, pre-dated to the visit);
          mask-closable=false — closes only via its buttons */}
      <Modal
        open={rxModalOpen}
        title="ثبت نسخه"
        closable={false}
        maskClosable={false}
        width="min(96vw, 640px)"
        footer={null}
        destroyOnHidden
        onCancel={() => setRxModalOpen(false)}
      >
        <PrescriptionForm
          form={rxForm}
          seed={rxSeed}
          submitting={addRx.isPending}
          onFinish={(v) =>
            addRx.mutate({
              prescribed_at: v.prescribed_at,
              notes: v.notes,
              items: v.items.map((row) => ({
                name: (row.name ?? '').trim() || undefined,
                quantity: row.quantity == null ? null : Number(row.quantity),
              })),
            })
          }
        />
      </Modal>
    </>
  )
})

export default AppointmentPanel
