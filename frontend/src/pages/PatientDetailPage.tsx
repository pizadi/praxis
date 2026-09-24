import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntApp,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Typography,
  Upload,
} from 'antd'
import type { UploadFile } from 'antd'
import { InboxOutlined } from '@ant-design/icons'

import { api, apiFieldErrors, apiError } from '../api/client'
import type {
  Appointment,
  AppointmentBrief,
  Attachment,
  Page,
  Patient,
  Prescription,
  QuestionnaireResponse,
  QuestionnaireTemplate,
} from '../api/types'
import type { Answers, FormatDoc } from '../lib/questionnaire'
import { faAnswerError, mergeResponse } from '../lib/questionnaire'
import { useUser } from '../components/AppLayout'
import { useBeforeUnloadGuard, useNavGuard } from '../components/NavGuard'
import { useIsMobile } from '../lib/useIsMobile'
import { JalaliDateTimePicker } from '../components/JalaliDates'
import AppointmentPanel, { type AppointmentPanelHandle } from '../components/AppointmentPanel'
import FileDetailPane from '../components/FileDetailPane'
import PatientFormModal from '../components/PatientFormModal'
import AppointmentSidebarCard from '../components/patient/AppointmentSidebarCard'
import FileSidebarCard from '../components/patient/FileSidebarCard'
import PatientInfoCard from '../components/patient/PatientInfoCard'
import PatientViewSwitcher, {
  type ViewMode,
} from '../components/patient/PatientViewSwitcher'
import PrescriptionSidebarCard from '../components/patient/PrescriptionSidebarCard'
import QuestionnaireSidebarCard from '../components/patient/QuestionnaireSidebarCard'
import { QuestionnaireForm, QuestionnaireView } from '../components/QuestionnaireRender'
import {
  PrescriptionForm,
  PrescriptionView,
  type PrescriptionFormValues,
} from '../components/PrescriptionRender'

/** A navigation the user requested while forms had unsaved changes. */
type PendingNav =
  | { kind: 'view'; view: ViewMode }
  | { kind: 'appt'; id: number | null }
  | { kind: 'route'; to: string }

const normVal = (v: unknown) => (v == null || v === '' ? null : v)

export default function PatientDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const { hasPerm } = useUser()
  const isMobile = useIsMobile()
  const { message } = AntApp.useApp()
  const qc = useQueryClient()

  const isAdmin = hasPerm('patients.delete')
  const isDoctor = hasPerm('appointments.delete')

  // selected appointment comes from the URL (?appt=123) so schedule/dashboard
  // links can deep-link straight into a patient + open appointment
  const selectedAppt = searchParams.get('appt')
    ? Number(searchParams.get('appt'))
    : null

  const [view, setView] = useState<ViewMode>('appointments')
  const [newApptOpen, setNewApptOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [apptForm] = Form.useForm<{ scheduled_at: string; notes?: string }>()

  // --- questionnaire view state ---
  const [qSelectedId, setQSelectedId] = useState<number | null>(null)
  const [qMode, setQMode] = useState<'view' | 'create' | 'edit'>('view')
  const [qPickTemplate, setQPickTemplate] = useState<number | null>(null)
  const [qForm] = Form.useForm<Record<string, unknown>>()

  // --- prescription view state ---
  const [rxSelectedId, setRxSelectedId] = useState<number | null>(null)
  const [rxMode, setRxMode] = useState<'view' | 'create' | 'edit'>('view')
  const [rxForm] = Form.useForm<PrescriptionFormValues>()

  // --- file upload modal state (files are patient-level) ---
  const [uploadOpen, setUploadOpen] = useState(false)
  const [uploadForm] = Form.useForm<{ description: string; notes: string }>()
  const [uploadList, setUploadList] = useState<UploadFile[]>([])

  // --- unsaved-changes guard state ---
  const [selectedFileId, setSelectedFileId] = useState<number | null>(null)
  const [pendingNav, setPendingNav] = useState<PendingNav | null>(null)
  const [apptDirty, setApptDirty] = useState(false)
  const apptPanelRef = useRef<AppointmentPanelHandle>(null)
  /** runs after a guard-initiated save succeeds (completes the navigation) */
  const afterSaveRef = useRef<(() => void) | null>(null)

  const { data: patient, isLoading } = useQuery({
    queryKey: ['patient', id],
    queryFn: async () => (await api.get<Patient>(`/patients/${id}`)).data,
  })

  const appts = useQuery({
    queryKey: ['patient-appointments', id],
    queryFn: async () =>
      (await api.get<Page<AppointmentBrief>>('/appointments', {
        params: { patient_id: id, limit: 100 },
      })).data,
  })

  const allFiles = useQuery({
    queryKey: ['patient-files', id],
    queryFn: async () =>
      (await api.get<Attachment[]>(`/patients/${id}/files`)).data,
    enabled: view === 'files',
  })

  const qCanRead = hasPerm('questionnaires.read')
  const qCanFill = hasPerm('questionnaires.fill')

  const qResponses = useQuery({
    queryKey: ['patient-questionnaires', id],
    queryFn: async () =>
      (await api.get<Page<QuestionnaireResponse>>(`/patients/${id}/questionnaires`, {
        params: { limit: 100 },
      })).data,
    enabled: view === 'questionnaires' && qCanRead,
  })

  const qTemplates = useQuery({
    queryKey: ['questionnaire-templates'],
    queryFn: async () =>
      (await api.get<Page<QuestionnaireTemplate>>('/questionnaires/templates', {
        params: { limit: 200 },
      })).data,
    enabled: view === 'questionnaires' && qCanRead,
  })

  // --- prescriptions queries/mutations ---
  const rxCanRead = hasPerm('prescriptions.read')
  const rxCanWrite = hasPerm('prescriptions.write')

  /** fresh-open state for the create form: one empty row + now */
  const rxCreateSeed: PrescriptionFormValues = useMemo(() => {
    const d = new Date()
    const p = (n: number) => String(n).padStart(2, '0')
    const tz = -d.getTimezoneOffset()
    const sign = tz >= 0 ? '+' : '-'
    const abs = Math.abs(tz)
    const nowIso = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(
      d.getHours(),
    )}:${p(d.getMinutes())}:00${sign}${p(Math.floor(abs / 60))}:${p(abs % 60)}`
    return { prescribed_at: nowIso, notes: '', items: [{ name: '' }] }
  }, [])

  const rxList = useQuery({
    queryKey: ['patient-prescriptions', id],
    queryFn: async () =>
      (await api.get<Page<Prescription>>(`/patients/${id}/prescriptions`, {
        params: { limit: 100 },
      })).data,
    enabled: view === 'prescriptions' && rxCanRead,
  })

  const afterRxSave = async () => {
    await qc.invalidateQueries({ queryKey: ['patient-prescriptions', id] })
    await qc.invalidateQueries({ queryKey: ['patient-prescriptions'] })
  }

  const createRx = useMutation({
    mutationFn: async (v: {
      prescribed_at?: string
      notes: string
      items: { item_id?: number; name?: string; quantity?: number | null }[]
    }) => (await api.post<Prescription>(`/patients/${id}/prescriptions`, v)).data,
    onSuccess: async (created) => {
      message.success('نسخه ثبت شد')
      setRxMode('view')
      setRxSelectedId(created.id)
      await afterRxSave()
      const next = afterSaveRef.current
      afterSaveRef.current = null
      next?.()
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const updateRx = useMutation({
    mutationFn: async (v: {
      rid: number
      prescribed_at?: string
      notes: string
      items: { item_id?: number; name?: string; quantity?: number | null }[]
    }) => (await api.patch<Prescription>(`/prescriptions/${v.rid}`, v)).data,
    onSuccess: async () => {
      message.success('نسخه به‌روزرسانی شد')
      setRxMode('view')
      await afterRxSave()
      const next = afterSaveRef.current
      afterSaveRef.current = null
      next?.()
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const deleteRx = useMutation({
    mutationFn: async (rid: number) => api.delete(`/prescriptions/${rid}`),
    onSuccess: async () => {
      message.success('به سبد بازیافت منتقل شد')
      setRxSelectedId(null)
      setRxMode('view')
      await afterRxSave()
    },
    onError: (err) => message.error(apiError(err).message),
  })

  // --- file upload (patient-level) ---
  const uploadFile = useMutation({
    mutationFn: async (payload: { values: { description: string; notes: string }; file?: File }) => {
      if (payload.file) {
        const fd = new FormData()
        fd.append('file', payload.file)
        fd.append('description', payload.values.description ?? '')
        fd.append('notes', payload.values.notes ?? '')
        return (await api.post(`/patients/${id}/files`, fd)).data
      }
      return (
        await api.post(`/patients/${id}/files/note`, {
          description: payload.values.description ?? '',
          notes: payload.values.notes ?? '',
        })
      ).data
    },
    onSuccess: async () => {
      message.success('ثبت شد')
      uploadForm.resetFields()
      setUploadList([])
      setUploadOpen(false)
      await qc.invalidateQueries({ queryKey: ['patient-files', id] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const addAppt = useMutation({
    mutationFn: async (values: { scheduled_at: string; notes?: string }) =>
      (
        await api.post<Appointment>(`/patients/${id}/appointments`, {
          scheduled_at: values.scheduled_at,
          notes: values.notes ?? '',
        })
      ).data,
    onSuccess: async (created) => {
      message.success('نوبت ثبت شد')
      setNewApptOpen(false)
      apptForm.resetFields()
      await qc.invalidateQueries({ queryKey: ['patient-appointments', id] })
      // open the new appointment's details right away (sidebar shows it selected)
      selectAppt(created.id)
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const deleteAppt = useMutation({
    mutationFn: async (apptId: number) => api.delete(`/appointments/${apptId}`),
    onSuccess: async () => {
      message.success('نوبت به سبد بازیافت منتقل شد')
      setSearchParams({})
      await qc.invalidateQueries({ queryKey: ['patient-appointments', id] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  // quick stage advance from the appointment sidebar (regression lives on
  // the appointment panel, behind a confirmation)
  const advanceStage = useMutation({
    mutationFn: async (apptId: number) =>
      api.patch(`/appointments/${apptId}/stage`, { direction: 'advance' }),
    onSuccess: async (_v, apptId) => {
      await qc.invalidateQueries({ queryKey: ['patient-appointments', id] })
      await qc.invalidateQueries({ queryKey: ['appointment', apptId] })
      await qc.invalidateQueries({ queryKey: ['schedule'] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const deletePatient = useMutation({
    mutationFn: async () => api.delete(`/patients/${id}`),
    onSuccess: () => {
      message.success('بیمار به سبد بازیافت منتقل شد')
      navigate('/patients')
    },
    onError: (err) => message.error(apiError(err).message),
  })

  // --- questionnaire mutations ---

  const afterQSave = async () => {
    await qc.invalidateQueries({ queryKey: ['patient-questionnaires', id] })
  }

  /** Surface server answer-validation errors inline, per field (the toast
   * alone carries no field information). */
  const showQErrors = (err: unknown) => {
    afterSaveRef.current = null
    const fields = apiFieldErrors(err)
    const entries = Object.entries(fields ?? {})
    if (entries.length > 0) {
      qForm.setFields(
        entries.map(([name, errors]) => ({
          name,
          errors: errors.map((m) => faAnswerError(m)),
        })),
      )
    }
    message.error(apiError(err).message)
  }

  const createQ = useMutation({
    mutationFn: async (v: { template_id: number; answers: Answers }) =>
      (await api.post<QuestionnaireResponse>(`/patients/${id}/questionnaires`, v)).data,
    onSuccess: async (created) => {
      message.success('پاسخ پرسش‌نامه ثبت شد')
      setQMode('view')
      setQPickTemplate(null)
      setQSelectedId(created.id)
      await afterQSave()
      const next = afterSaveRef.current
      afterSaveRef.current = null
      next?.()
    },
    onError: showQErrors,
  })

  const updateQ = useMutation({
    mutationFn: async (v: { rid: number; answers: Answers }) =>
      (await api.patch<QuestionnaireResponse>(`/questionnaires/responses/${v.rid}`, {
        answers: v.answers,
      })).data,
    onSuccess: async () => {
      message.success('پاسخ‌ها به‌روزرسانی شد')
      setQMode('view')
      await afterQSave()
      const next = afterSaveRef.current
      afterSaveRef.current = null
      next?.()
    },
    onError: showQErrors,
  })

  const deleteQ = useMutation({
    mutationFn: async (rid: number) => api.delete(`/questionnaires/responses/${rid}`),
    onSuccess: async () => {
      message.success('به سبد بازیافت منتقل شد')
      setQSelectedId(null)
      setQMode('view')
      await afterQSave()
    },
    onError: (err) => message.error(apiError(err).message),
  })

  /** Clear fields invalid against the current template: known-but-invalid
   * keys → null, removed keys dropped; valid answers preserved. */
  const clearInvalidQ = useMutation({
    mutationFn: async (r: QuestionnaireResponse) => {
      const fmt = (qTemplates.data?.items ?? []).find((t) => t.id === r.template_id)
        ?.format as FormatDoc | undefined
      if (!fmt) throw new Error('قالب پرسش‌نامه یافت نشد')
      const merged = mergeResponse(fmt, r.answers)
      const next: Answers = {}
      for (const q of fmt.questions ?? []) {
        const v = r.answers?.[q.key]
        if (v === undefined) continue // treat as empty
        next[q.key] = merged.invalidKeys.includes(q.key) ? null : v
      }
      return (
        await api.patch<QuestionnaireResponse>(`/questionnaires/responses/${r.id}`, {
          answers: next,
        })
      ).data
    },
    onSuccess: async () => {
      message.success('فیلدهای نامعتبر پاک شدند')
      await afterQSave()
    },
    onError: (err) => message.error(apiError(err).message),
  })

  // selected questionnaire + template (before the early return: the dirty
  // guard below watches the form and needs them unconditionally)
  const selectedQ = (qResponses.data?.items ?? []).find((r) => r.id === qSelectedId) ?? null
  const selectedQTemplate = selectedQ
    ? ((qTemplates.data?.items ?? []).find((t) => t.id === selectedQ.template_id) ?? null)
    : null
  const createTemplate = qPickTemplate
    ? ((qTemplates.data?.items ?? []).find((t) => t.id === qPickTemplate) ?? null)
    : null

  // selected prescription (same reasoning: needed by the dirty watch)
  const selectedRx =
    (rxList.data?.items ?? []).find((r) => r.id === rxSelectedId) ?? null

  // --- unsaved-changes detection ---------------------------------------------
  // appointment notes: reported by AppointmentPanel via onDirtyChange
  // questionnaire answers: watched here (the form instance is parent-owned)
  const qValues = Form.useWatch([], qForm)
  const qDirty = useMemo(() => {
    if (qMode === 'view' || !qValues) return false
    if (qMode === 'create') {
      return Object.values(qValues).some((v) => v != null && v !== '')
    }
    if (!selectedQ) return false
    const stored = selectedQ.answers ?? {}
    const keys = new Set([...Object.keys(stored), ...Object.keys(qValues)])
    for (const k of keys) {
      if (normVal(stored[k]) !== normVal(qValues[k])) return true
    }
    return false
  }, [qMode, qValues, selectedQ])

  // prescription rows: watched here (parent-owned form instance)
  const rxValues = Form.useWatch([], rxForm)
  const rxDirty = useMemo(() => {
    if (rxMode === 'view' || !rxValues) return false
    if (rxMode === 'create') {
      return (
        (rxValues.items ?? []).some((r) => (r?.name ?? '').trim() !== '') ||
        (rxValues.notes ?? '') !== ''
      )
    }
    if (!selectedRx) return false
    const storedNames = selectedRx.items.map((it) => it.item_name)
    const formNames = (rxValues.items ?? []).map((r) => (r?.name ?? '').trim())
    if (
      storedNames.length !== formNames.length ||
      storedNames.some((n, i) => n !== formNames[i])
    ) return true
    if ((rxValues.notes ?? '') !== (selectedRx.notes ?? '')) return true
    return (rxValues.items ?? []).some((r, i) => {
      const storedQty = selectedRx.items[i]?.quantity ?? null
      const formQty = r?.quantity == null ? null : Number(r.quantity)
      return storedQty !== formQty
    })
  }, [rxMode, rxValues, selectedRx])

  const dirty = apptDirty || qDirty || rxDirty

  const applyNav = useCallback((t: PendingNav | null) => {
    if (t == null) return
    if (t.kind === 'view') {
      setView(t.view)
      setQMode('view')
      setQSelectedId(null)
      setQPickTemplate(null)
    } else if (t.kind === 'route') {
      navigate(t.to)
    } else if (t.id == null) {
      setSearchParams({})
    } else {
      setSearchParams({ appt: String(t.id) })
    }
  }, [navigate, setSearchParams])

  /** Route navigations through the unsaved-changes confirmation. */
  const requestNav = useCallback(
    (t: PendingNav) => {
      if (dirty) setPendingNav(t)
      else applyNav(t)
    },
    [dirty, applyNav],
  )

  // guard sidebar-menu navigations + tab close while dirty
  const { registerNavBlocker } = useNavGuard()
  const dirtyRef = useRef(dirty)
  dirtyRef.current = dirty
  useEffect(() => {
    registerNavBlocker({
      isDirty: () => dirtyRef.current,
      requestLeave: (to: string) => setPendingNav({ kind: 'route', to }),
    })
    return () => registerNavBlocker(null)
  }, [registerNavBlocker])
  useBeforeUnloadGuard(dirty)

  if (isLoading || !patient) {
    return <Card loading />
  }

  const items = appts.data?.items ?? [] // newest → oldest (server-ordered)

  const openNewAppt = () => {
    const now = new Date()
    const p = (n: number) => String(n).padStart(2, '0')
    const tz = -now.getTimezoneOffset()
    const sign = tz >= 0 ? '+' : '-'
    const abs = Math.abs(tz)
    const nowIso = `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}T${p(
      now.getHours(),
    )}:${p(now.getMinutes())}:00${sign}${p(Math.floor(abs / 60))}:${p(abs % 60)}`
    apptForm.setFieldsValue({ scheduled_at: nowIso, notes: '' })
    setNewApptOpen(true)
  }

  const selectAppt = (apptId: number | null) => {
    requestNav({ kind: 'appt', id: apptId })
  }

  const selectedFile =
    (allFiles.data ?? []).find((f) => f.id === selectedFileId) ?? null

  /** Guard-initiated save: submit the active dirty form; its onSuccess hook
   * completes the pending navigation via afterSaveRef. */
  const saveActiveForm = () => {
    const target = pendingNav
    setPendingNav(null)
    if (target == null) return
    afterSaveRef.current = () => applyNav(target)
    if (rxDirty) rxForm.submit()
    else if (qDirty) qForm.submit()
    else apptPanelRef.current?.save()
  }

  const discardAndNav = () => {
    const target = pendingNav
    setPendingNav(null)
    afterSaveRef.current = null
    if (rxDirty) rxForm.resetFields()
    if (qDirty) qForm.resetFields()
    if (apptDirty) apptPanelRef.current?.reset()
    applyNav(target)
  }

  return (
    <Row gutter={[16, 16]} style={{ minHeight: 'calc(100vh - 112px)' }}>
      {/* ---------- sidebar: patient info + views ---------- */}
      <Col xs={24} md={7}>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <PatientInfoCard
            patient={patient}
            canDelete={isAdmin}
            onEdit={() => setEditOpen(true)}
            onDelete={() => deletePatient.mutate()}
          />

          <PatientViewSwitcher
            value={view}
            onChange={(next) => requestNav({ kind: 'view', view: next })}
          />

          {view === 'appointments' && (
            <AppointmentSidebarCard
              appointments={items}
              loading={appts.isLoading}
              selectedId={selectedAppt}
              canStage={hasPerm('appointments.stage')}
              canDelete={isDoctor}
              advancingId={advanceStage.variables}
              onSelect={selectAppt}
              onAdvance={(appointmentId) => advanceStage.mutate(appointmentId)}
              onDelete={(appointmentId) => deleteAppt.mutate(appointmentId)}
              onNew={openNewAppt}
            />
          )}

          {view === 'files' && (
            <FileSidebarCard
              files={allFiles.data ?? []}
              loading={allFiles.isLoading}
              selectedId={selectedFileId}
              canWrite={hasPerm('files.write')}
              isMobile={isMobile}
              onSelect={setSelectedFileId}
              onNew={() => setUploadOpen(true)}
            />
          )}

          {view === 'prescriptions' && (
            <PrescriptionSidebarCard
              prescriptions={rxList.data?.items ?? []}
              loading={rxList.isLoading}
              selectedId={rxSelectedId}
              canWrite={rxCanWrite}
              onSelect={(prescriptionId) => {
                setRxSelectedId(prescriptionId)
                setRxMode('view')
              }}
              onDelete={(prescriptionId) => deleteRx.mutate(prescriptionId)}
              onNew={() => {
                setRxMode('create')
                setRxSelectedId(null)
              }}
            />
          )}

          {view === 'questionnaires' && (
            <QuestionnaireSidebarCard
              responses={qResponses.data?.items ?? []}
              loading={qResponses.isLoading}
              selectedId={qSelectedId}
              canFill={qCanFill}
              templatesTotal={qTemplates.data?.total ?? 0}
              onSelect={(responseId) => {
                setQSelectedId(responseId)
                setQMode('view')
                setQPickTemplate(null)
              }}
              onDelete={(responseId) => deleteQ.mutate(responseId)}
              onNew={() => {
                setQMode('create')
                setQSelectedId(null)
                setQPickTemplate(null)
              }}
            />
          )}
        </Space>
      </Col>

      {/* ---------- main pane (visually left in RTL) ---------- */}
      <Col xs={24} md={17}>
        {view === 'appointments' &&
          (selectedAppt == null ? (
            <Card>
              <Empty
                description="برای مشاهده جزئیات، یک نوبت از فهرست انتخاب کنید"
                style={{ marginTop: 80 }}
              />
            </Card>
          ) : (
            <AppointmentPanel
              key={selectedAppt}
              ref={apptPanelRef}
              appointmentId={selectedAppt}
              onDirtyChange={setApptDirty}
              onSaved={() => {
                const next = afterSaveRef.current
                afterSaveRef.current = null
                next?.()
              }}
              onSaveFailed={() => {
                afterSaveRef.current = null
              }}
            />
          ))}

        {view === 'files' &&
          (selectedFile == null ? (
            <Card>
              <Empty
                description="برای مشاهده جزئیات، یک فایل از فهرست انتخاب کنید"
                style={{ marginTop: 80 }}
              />
            </Card>
          ) : (
            <FileDetailPane file={selectedFile} />
          ))}

        {view === 'questionnaires' && (
          <Card
            title={
              qMode === 'create'
                ? 'ثبت پرسش‌نامه جدید'
                : selectedQ
                  ? selectedQ.template_name
                  : 'پرسش‌نامه‌ها'
            }
          >
            {!qCanRead ? (
              <Empty description="دسترسی مشاهده پرسش‌نامه‌ها را ندارید" style={{ marginTop: 80 }} />
            ) : qMode === 'create' ? (
              !createTemplate ? (
                <Space direction="vertical" style={{ width: '100%' }} size="middle">
                  <Typography.Text>یک قالب انتخاب کنید:</Typography.Text>
                  <Select<number>
                    showSearch
                    optionFilterProp="label"
                    placeholder="قالب پرسش‌نامه"
                    style={{ width: '100%', maxWidth: 320 }}
                    value={qPickTemplate ?? undefined}
                    onChange={setQPickTemplate}
                    options={(qTemplates.data?.items ?? []).map((t) => ({
                      value: t.id,
                      label: t.name,
                    }))}
                  />
                </Space>
              ) : (
                <QuestionnaireForm
                  form={qForm}
                  format={createTemplate.format as FormatDoc}
                  submitting={createQ.isPending}
                  onFinish={(answers) =>
                    createQ.mutate({ template_id: createTemplate.id, answers })
                  }
                />
              )
            ) : selectedQ == null ? (
              <Empty
                description="برای مشاهده یا ثبت پرسش‌نامه، از فهرست انتخاب کنید یا «پرسش‌نامه جدید» را بزنید"
                style={{ marginTop: 80 }}
              />
            ) : selectedQTemplate == null ? (
              <Typography.Text type="warning">
                قالب این پاسخ یافت نشد (قالب حذف شده است).
              </Typography.Text>
            ) : qMode === 'edit' ? (
              <QuestionnaireForm
                form={qForm}
                format={selectedQTemplate.format as FormatDoc}
                initialAnswers={selectedQ.answers}
                submitting={updateQ.isPending}
                onFinish={(answers) =>
                  updateQ.mutate({ rid: selectedQ.id, answers })
                }
              />
            ) : (
              <QuestionnaireView
                format={selectedQTemplate.format as FormatDoc}
                answers={selectedQ.answers}
                clearing={clearInvalidQ.isPending}
                onClearInvalid={
                  qCanFill && mergeResponse(
                    selectedQTemplate.format as FormatDoc,
                    selectedQ.answers,
                  ).invalidKeys.length > 0
                    ? () => clearInvalidQ.mutate(selectedQ)
                    : undefined
                }
                onEdit={qCanFill ? () => setQMode('edit') : undefined}
              />
            )}
          </Card>
        )}
        {view === 'prescriptions' && (
          <Card
            title={
              rxMode === 'create'
                ? 'ثبت نسخه جدید'
                : rxMode === 'edit'
                  ? 'ویرایش نسخه'
                  : 'نسخه‌ها'
            }
          >
            {!rxCanRead ? (
              <Empty description="دسترسی مشاهده نسخه‌ها را ندارید" style={{ marginTop: 80 }} />
            ) : rxMode === 'create' ? (
              <PrescriptionForm
                form={rxForm}
                seed={rxCreateSeed}
                submitting={createRx.isPending}
                onFinish={(v) => createRx.mutate(v)}
              />
            ) : selectedRx == null ? (
              <Empty
                description="برای مشاهده یا ثبت نسخه، از فهرست انتخاب کنید یا «نسخه جدید» را بزنید"
                style={{ marginTop: 80 }}
              />
            ) : rxMode === 'edit' ? (
              <PrescriptionForm
                form={rxForm}
                initial={selectedRx}
                submitting={updateRx.isPending}
                onFinish={(v) => updateRx.mutate({ rid: selectedRx.id, ...v })}
              />
            ) : (
              <PrescriptionView
                rx={selectedRx}
                onEdit={rxCanWrite ? () => setRxMode('edit') : undefined}
              />
            )}
          </Card>
        )}
      </Col>

      {/* ---------- unsaved-changes confirmation (forced choice) ---------- */}
      <Modal
        open={pendingNav != null}
        title="تغییرات ذخیره نشده"
        closable={false}
        maskClosable={false}
        width="min(96vw, 440px)"
        footer={
          <Space wrap style={{ justifyContent: 'space-between', width: '100%' }}>
            <Button onClick={() => setPendingNav(null)}>بازگشت به ویرایش</Button>
            <Space>
              <Button
                danger
                onClick={() => {
                  discardAndNav()
                }}
              >
                دورریختن تغییرات
              </Button>
              <Button type="primary" onClick={saveActiveForm}>
                ذخیره و ادامه
              </Button>
            </Space>
          </Space>
        }
      >
        یکی از فرم‌ها تغییرات ذخیره‌نشده دارد. قبل از رفتن به بخش دیگر چه کاری
        انجام شود؟
      </Modal>

      {/* ---------- new appointment modal (Jalali, defaults to now) ---------- */}
      <Modal
        open={newApptOpen}
        title="ثبت نوبت جدید"
        okText="ثبت"
        cancelText="انصراف"
        maskClosable={false}
        onCancel={() => setNewApptOpen(false)}
        confirmLoading={addAppt.isPending}
        onOk={() => apptForm.submit()}
        destroyOnHidden
      >
        <Form form={apptForm} layout="vertical" onFinish={(v) => addAppt.mutate(v)}>
          <Form.Item
            name="scheduled_at"
            label="زمان نوبت"
            rules={[{ required: true, message: 'زمان الزامی است' }]}
          >
            <JalaliDateTimePicker />
          </Form.Item>
          <Form.Item name="notes" label="یادداشت">
            <Input.TextArea rows={2} placeholder="اختیاری" />
          </Form.Item>
        </Form>
      </Modal>

      {/* ---------- upload file modal (files are patient-level since 1.3) ---------- */}
      <Modal
        open={uploadOpen}
        title="افزودن فایل"
        okText="ذخیره"
        cancelText="انصراف"
        maskClosable={false}
        onCancel={() => setUploadOpen(false)}
        confirmLoading={uploadFile.isPending}
        onOk={() => uploadForm.submit()}
        destroyOnHidden
      >
        <Form
          form={uploadForm}
          layout="vertical"
          onFinish={(v: { description: string; notes: string }) => {
            const f = uploadList[0]?.originFileObj
            if (f) uploadFile.mutate({ values: v, file: f })
            else uploadFile.mutate({ values: v })
          }}
        >
          <Form.Item
            name="description"
            label="شرح"
            rules={[{ required: true, message: 'شرح الزامی است' }]}
          >
            <Input maxLength={128} placeholder="مثلاً گزارش آزمایش" />
          </Form.Item>
          <Form.Item name="notes" label="یادداشت">
            <Input.TextArea rows={2} maxLength={10000} placeholder="اختیاری" />
          </Form.Item>
          <Form.Item label="فایل (اختیاری — بدون فایل، فقط شرح و یادداشت ثبت می‌شود)">
            <Upload
              maxCount={1}
              fileList={uploadList}
              beforeUpload={() => false}
              onChange={({ fileList }) => setUploadList(fileList.slice(-1))}
            >
              <Button icon={<InboxOutlined />}>انتخاب فایل…</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>

      {/* ---------- edit patient modal ---------- */}
      <PatientFormModal
        open={editOpen}
        patient={patient}
        onCancel={() => setEditOpen(false)}
        onDone={() => setEditOpen(false)}
      />
    </Row>
  )
}
