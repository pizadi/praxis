import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntApp,
  Badge,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Popconfirm,
  Row,
  Segmented,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import {
  DeleteOutlined,
  EditOutlined,
  FileOutlined,
  PaperClipOutlined,
  PlusOutlined,
  WalletOutlined,
} from '@ant-design/icons'

import { api, apiError } from '../api/client'
import type {
  Appointment,
  AppointmentBrief,
  Attachment,
  NamedRef,
  Page,
  Patient,
  PatientTransaction,
} from '../api/types'
import { fileSize, formatJalali, formatJalaliTime, formatMoney, toFaDigits } from '../lib/jalali'
import { useUser } from '../components/AppLayout'
import { JalaliDateTimePicker } from '../components/JalaliDates'
import AppointmentPanel from '../components/AppointmentPanel'
import FileNotesExpanded from '../components/FileNotesExpanded'
import PatientFormModal from '../components/PatientFormModal'

type ViewMode = 'appointments' | 'files' | 'payments'

export default function PatientDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const { hasPerm } = useUser()
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
      (await api.get<Page<Attachment>>(`/patients/${id}/all-files`, {
        params: { limit: 100 },
      })).data,
    enabled: view === 'files',
  })

  const allTxns = useQuery({
    queryKey: ['patient-txns', id],
    queryFn: async () =>
      (await api.get<Page<PatientTransaction>>(`/patients/${id}/all-transactions`, {
        params: { limit: 100 },
      })).data,
    enabled: view === 'payments',
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

  const deletePatient = useMutation({
    mutationFn: async () => api.delete(`/patients/${id}`),
    onSuccess: () => {
      message.success('بیمار به سبد بازیافت منتقل شد')
      navigate('/patients')
    },
    onError: (err) => message.error(apiError(err).message),
  })

  useEffect(() => {
    if (patient && selectedAppt == null && view === 'appointments') {
      // nothing — keep the empty-state hint until the user picks one
    }
  }, [patient, selectedAppt, view])

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
    if (apptId == null) setSearchParams({})
    else setSearchParams({ appt: String(apptId) })
  }

  return (
    <Row gutter={16} style={{ minHeight: 'calc(100vh - 112px)' }}>
      {/* ---------- sidebar: patient info + views ---------- */}
      <Col span={7}>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Card
            title={`${patient.first_name} ${patient.last_name}`}
            extra={
              <Space>
                <Button
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => setEditOpen(true)}
                >
                  ویرایش
                </Button>
                {isAdmin && (
                  <Popconfirm
                    title="بیمار به سبد بازیافت منتقل شود؟ (نوبت‌ها و فایل‌ها پنهان می‌شوند)"
                    onConfirm={() => deletePatient.mutate()}
                  >
                    <Button size="small" danger icon={<DeleteOutlined />}>
                      حذف
                    </Button>
                  </Popconfirm>
                )}
              </Space>
            }
          >
            <Descriptions bordered column={1} size="small">
              <Descriptions.Item label="کد ملی">
                {toFaDigits(patient.national_id)}
              </Descriptions.Item>
              <Descriptions.Item label="تلفن">
                {toFaDigits(patient.phone_number) || '—'}
              </Descriptions.Item>
              <Descriptions.Item label="بیمه">{patient.insurance || '—'}</Descriptions.Item>
              <Descriptions.Item label="سال تولد">
                {toFaDigits(patient.year_of_birth)}
              </Descriptions.Item>
              <Descriptions.Item label="جنسیت">
                {patient.gender === 0 ? 'مرد' : 'زن'}
              </Descriptions.Item>
              <Descriptions.Item label="برچسب‌ها">
                <Space wrap>
                  {patient.tags.length === 0 && patient.diagnoses.length === 0 && '—'}
                  {patient.tags.map((t: NamedRef) => (
                    <Tag key={t.id} color="blue">
                      {t.name}
                    </Tag>
                  ))}
                  {patient.diagnoses.map((d: NamedRef) => (
                    <Tag key={d.id} color="red">
                      {d.name}
                    </Tag>
                  ))}
                </Space>
              </Descriptions.Item>
            </Descriptions>
          </Card>

          {/* view switcher: appointments / all files / all payments */}
          <Segmented<ViewMode>
            block
            value={view}
            onChange={(v) => setView(v)}
            options={[
              { value: 'appointments', label: 'نوبت‌ها', icon: <PlusOutlined /> },
              { value: 'files', label: 'همه فایل‌ها', icon: <FileOutlined /> },
              { value: 'payments', label: 'همه پرداخت‌ها', icon: <WalletOutlined /> },
            ]}
          />

          {view === 'appointments' && (
            <Card
              title="نوبت‌ها"
              extra={
                <Button
                  type="primary"
                  size="small"
                  icon={<PlusOutlined />}
                  onClick={openNewAppt}
                >
                  نوبت جدید
                </Button>
              }
              styles={{ body: { padding: 0, maxHeight: '48vh', overflowY: 'auto' } }}
            >
              <List
                loading={appts.isLoading}
                dataSource={items}
                locale={{ emptyText: <Empty description="نوبتی ثبت نشده است" /> }}
                renderItem={(a) => (
                  <List.Item
                    style={{
                      cursor: 'pointer',
                      paddingInline: 16,
                      background: selectedAppt === a.id ? '#e6f4ff' : undefined,
                    }}
                    onClick={() => selectAppt(a.id)}
                  >
                    <Space
                      style={{ width: '100%', justifyContent: 'space-between' }}
                    >
                      <Space direction="vertical" size={0}>
                        <Typography.Text strong>
                          {formatJalali(a.scheduled_at)}
                        </Typography.Text>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          ساعت {formatJalaliTime(a.scheduled_at)}
                        </Typography.Text>
                      </Space>
                      <Space>
                        {a.attachment_count > 0 && (
                          <Badge count={a.attachment_count} size="small" color="blue">
                            <PaperClipOutlined
                              style={{ fontSize: 16, color: '#1677ff' }}
                            />
                          </Badge>
                        )}
                        {isDoctor && (
                          <Popconfirm
                            title="نوبت به سبد بازیافت منتقل شود؟"
                            onConfirm={(e) => {
                              e?.stopPropagation()
                              deleteAppt.mutate(a.id)
                            }}
                            onCancel={(e) => e?.stopPropagation()}
                          >
                            <Button
                              size="small"
                              type="text"
                              danger
                              icon={<DeleteOutlined />}
                              onClick={(e) => e.stopPropagation()}
                            />
                          </Popconfirm>
                        )}
                      </Space>
                    </Space>
                  </List.Item>
                )}
              />
            </Card>
          )}

          {view === 'files' && (
            <Card title="همه فایل‌ها" styles={{ body: { padding: 0 } }}>
              <Table<Attachment>
                rowKey="id"
                size="small"
                loading={allFiles.isLoading}
                dataSource={allFiles.data?.items ?? []}
                pagination={
                  (allFiles.data?.total ?? 0) > 100
                    ? { pageSize: 100 }
                    : false
                }
                locale={{ emptyText: 'فایلی موجود نیست' }}
                expandable={{
                  expandedRowRender: (f) => <FileNotesExpanded file={f} />,
                  rowExpandable: (f) => isDoctor || !!f.notes.trim(),
                }}
                onRow={(f) => ({
                  onClick: (e) => {
                    // clicking the expand chevron must not jump to the appointment
                    if ((e.target as HTMLElement).closest('.ant-table-row-expand-icon'))
                      return
                    selectAppt(f.appointment_id)
                  },
                  style: { cursor: 'pointer' },
                })}
                columns={[
                  {
                    title: 'نوبت',
                    dataIndex: 'appointment_id',
                    render: (aid: number) => {
                      const ap = items.find((x) => x.id === aid)
                      return ap ? formatJalali(ap.scheduled_at) : `#${aid}`
                    },
                  },
                  { title: 'شرح', dataIndex: 'description' },
                  {
                    title: 'نام فایل',
                    dataIndex: 'original_filename',
                    render: (name: string | null) =>
                      name ?? (
                        <Typography.Text type="secondary">بدون فایل</Typography.Text>
                      ),
                  },
                  { title: 'حجم', dataIndex: 'size_bytes', render: fileSize },
                ]}
              />
            </Card>
          )}

          {view === 'payments' && (
            <Card
              title="همه پرداخت‌ها"
              styles={{ body: { padding: 0 } }}
              extra={
                <Typography.Text strong>
                  جمع:{' '}
                  {formatMoney(
                    (allTxns.data?.items ?? []).reduce((s, t) => s + t.amount, 0),
                  )}
                </Typography.Text>
              }
            >
              <Table<PatientTransaction>
                rowKey="id"
                size="small"
                loading={allTxns.isLoading}
                dataSource={allTxns.data?.items ?? []}
                pagination={
                  (allTxns.data?.total ?? 0) > 100 ? { pageSize: 100 } : false
                }
                locale={{ emptyText: 'پرداختی ثبت نشده است' }}
                onRow={(t) => ({
                  onClick: () => selectAppt(t.appointment_id),
                  style: { cursor: 'pointer' },
                })}
                columns={[
                  {
                    title: 'نوبت',
                    dataIndex: 'appointment_scheduled_at',
                    render: (v: string) => formatJalali(v),
                  },
                  { title: 'شرح', dataIndex: 'description' },
                  { title: 'مبلغ', dataIndex: 'amount', render: formatMoney },
                  {
                    title: 'نوع',
                    dataIndex: 'pos',
                    render: (pos: boolean) => (pos ? 'کارت‌خوان' : 'نقدی'),
                  },
                ]}
              />
            </Card>
          )}
        </Space>
      </Col>

      {/* ---------- main pane: selected appointment detail ---------- */}
      <Col span={17}>
        {view !== 'appointments' ? (
          <Card>
            <Empty
              description={
                view === 'files'
                  ? 'برای دیدن جزئیات یک فایل، نوبت مربوطه را انتخاب کنید'
                  : 'برای دیدن جزئیات یک پرداخت، نوبت مربوطه را انتخاب کنید'
              }
              style={{ marginTop: 80 }}
            />
          </Card>
        ) : selectedAppt == null ? (
          <Card>
            <Empty
              description="برای مشاهده جزئیات، یک نوبت از فهرست انتخاب کنید"
              style={{ marginTop: 80 }}
            />
          </Card>
        ) : (
          <AppointmentPanel appointmentId={selectedAppt} />
        )}
      </Col>

      {/* ---------- new appointment modal (Jalali, defaults to now) ---------- */}
      <Modal
        open={newApptOpen}
        title="ثبت نوبت جدید"
        okText="ثبت"
        cancelText="انصراف"
        onCancel={() => setNewApptOpen(false)}
        confirmLoading={addAppt.isPending}
        onOk={() => apptForm.submit()}
        destroyOnClose
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
