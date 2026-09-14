import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntApp,
  AutoComplete,
  Button,
  Card,
  Col,
  Form,
  Input,
  Modal,
  Popconfirm,
  Radio,
  Row,
  Space,
  Statistic,
  Table,
  Tabs,
  Typography,
  Upload,
} from 'antd'
import type { UploadFile } from 'antd'
import {
  DeleteOutlined,
  DownloadOutlined,
  FileTextOutlined,
  InboxOutlined,
} from '@ant-design/icons'
import { useSearchParams } from 'react-router-dom'

import { API_BASE, api, apiError, getAccessToken } from '../api/client'
import type { Appointment, Attachment, Page, Transaction } from '../api/types'
import { fileSize, formatMoney } from '../lib/jalali'
import { useUser } from './AppLayout'
import FileNotesExpanded from './FileNotesExpanded'

/**
 * Full detail view of one appointment (notes / files / payments tabs).
 * Used both by the standalone /appointments/:id page and embedded in the
 * patient detail page's main pane.
 */
export default function AppointmentPanel({ appointmentId }: { appointmentId: number }) {
  const { isDoctor } = useUser()
  const { message } = AntApp.useApp()
  const qc = useQueryClient()
  const [, setSearchParams] = useSearchParams()

  const appt = useQuery({
    queryKey: ['appointment', appointmentId],
    queryFn: async () => (await api.get<Appointment>(`/appointments/${appointmentId}`)).data,
  })

  const files = useQuery({
    queryKey: ['appointment-files', appointmentId],
    queryFn: async () => (await api.get<Attachment[]>(`/appointments/${appointmentId}/files`)).data,
  })

  const txns = useQuery({
    queryKey: ['appointment-txns', appointmentId],
    queryFn: async () =>
      (await api.get<Page<Transaction>>(`/appointments/${appointmentId}/transactions`, {
        params: { limit: 100 },
      })).data,
  })

  const [notesForm] = Form.useForm<Appointment>()
  const [txnForm] = Form.useForm<{ description: string; amount: number; pos: boolean }>()
  const [noteFileOpen, setNoteFileOpen] = useState(false)
  const [noteFileForm] = Form.useForm<{ description: string; notes: string }>()

  const saveNotes = useMutation({
    mutationFn: async (values: Partial<Appointment>) =>
      api.patch(`/appointments/${appointmentId}`, values),
    onSuccess: () => {
      message.success('ذخیره شد')
      qc.invalidateQueries({ queryKey: ['appointment', appointmentId] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const addTxn = useMutation({
    mutationFn: async (v: { description: string; amount: number; pos: boolean }) =>
      api.post(`/appointments/${appointmentId}/transactions`, v),
    onSuccess: () => {
      message.success('تراکنش ثبت شد')
      txnForm.resetFields()
      qc.invalidateQueries({ queryKey: ['appointment-txns', appointmentId] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const delTxn = useMutation({
    mutationFn: async (txnId: number) => api.delete(`/appointments/transactions/${txnId}`),
    onSuccess: () => {
      message.success('به سبد بازیافت منتقل شد')
      qc.invalidateQueries({ queryKey: ['appointment-txns', appointmentId] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const delFile = useMutation({
    mutationFn: async (fileId: number) => api.delete(`/appointments/files/${fileId}`),
    onSuccess: () => {
      message.success('فایل به سبد بازیافت منتقل شد')
      qc.invalidateQueries({ queryKey: ['appointment-files', appointmentId] })
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

  const addNoteFile = useMutation({
    mutationFn: async (values: { description: string; notes: string }) =>
      api.post(`/appointments/${appointmentId}/files/note`, values),
    onSuccess: async () => {
      message.success('ثبت شد')
      setNoteFileOpen(false)
      noteFileForm.resetFields()
      await qc.invalidateQueries({ queryKey: ['appointment-files', appointmentId] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const openNoteFileModal = () => {
    noteFileForm.resetFields()
    setNoteFileOpen(true)
  }

  const downloadFile = async (fileId: number, name: string | null) => {    try {
      const res = await api.get(`/appointments/files/${fileId}/download`, {
        responseType: 'blob',
      })
      const url = URL.createObjectURL(res.data)
      const link = document.createElement('a')
      link.href = url
      link.download = name ?? 'file'
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      message.error(apiError(err).message)
    }
  }

  const [uploadDesc, setUploadDesc] = useState('')
  const [uploadNotes, setUploadNotes] = useState('')

  const uploadProps = {
    name: 'file',
    action: `${API_BASE}/appointments/${appointmentId}/files`,
    headers: { Authorization: `Bearer ${getAccessToken() ?? ''}` },
    // resolved at submit time so the current input values are always sent
    data: () => ({ description: uploadDesc, notes: uploadNotes }),
    onChange(info: { file: UploadFile }) {
      if (info.file.status === 'done') {
        message.success('فایل بارگذاری شد')
        setUploadDesc('')
        setUploadNotes('')
        qc.invalidateQueries({ queryKey: ['appointment-files', appointmentId] })
      } else if (info.file.status === 'error') {
        // antd gives us the raw XHR; surface the backend's error envelope
        let msg = 'بارگذاری ناموفق'
        try {
          const xhr = info.file.xhr as XMLHttpRequest | undefined
          const body = xhr?.responseText ? JSON.parse(xhr.responseText) : null
          msg = body?.error?.message ?? msg
        } catch {
          // keep the default message
        }
        message.error(msg)
      }
    },
  }

  if (appt.isLoading || !appt.data) {
    return <Card loading />
  }
  const a = appt.data

  return (
    <>
      <Tabs
        tabBarExtraContent={
          isDoctor && (
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
          children: isDoctor ? (
            <Form
              form={notesForm}
              layout="vertical"
              initialValues={{ notes: a.notes, cm: a.cm, hx: a.hx, px: a.px, rx: a.rx }}
              onFinish={(v) => saveNotes.mutate(v)}
            >
              <Form.Item name="notes" label="یادداشت">
                <Input.TextArea rows={2} />
              </Form.Item>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item name="cm" label="CC / شرح حال فعلی">
                    <Input.TextArea rows={3} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="hx" label="Hx — تاریخچه">
                    <Input.TextArea rows={3} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="px" label="Px — معاینه">
                    <Input.TextArea rows={3} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="rx" label="Rx — نسخه">
                    <Input.TextArea rows={3} />
                  </Form.Item>
                </Col>
              </Row>
              <Button type="primary" htmlType="submit" loading={saveNotes.isPending}>
                ذخیره
              </Button>
            </Form>
          ) : (
            <Typography.Text type="secondary">
              دسترسی پذیرش به یادداشت‌های پزشکی محدود است
            </Typography.Text>
          ),
        },
        {
          key: 'files',
          label: `فایل‌ها (${files.data?.length ?? 0})`,
          children: (
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              {isDoctor && (
                <Space direction="vertical" style={{ width: '100%' }} size="small">
                  <Input
                    placeholder="شرح فایل (اختیاری)"
                    maxLength={128}
                    value={uploadDesc}
                    onChange={(e) => setUploadDesc(e.target.value)}
                  />
                  <Input.TextArea
                    placeholder="یادداشت فایل (اختیاری)"
                    rows={2}
                    maxLength={10000}
                    value={uploadNotes}
                    onChange={(e) => setUploadNotes(e.target.value)}
                  />
                  <Upload.Dragger {...uploadProps}>
                    <p className="ant-upload-drag-icon">
                      <InboxOutlined />
                    </p>
                    <p className="ant-upload-text">فایل را اینجا رها کنید</p>
                  </Upload.Dragger>
                  <Button
                    icon={<FileTextOutlined />}
                    onClick={openNoteFileModal}
                  >
                    ثبت شرح و یادداشت بدون فایل
                  </Button>
                </Space>
              )}
              <Table<Attachment>
                rowKey="id"
                dataSource={files.data ?? []}
                pagination={false}
                size="small"
                expandable={{
                  expandedRowRender: (f) => <FileNotesExpanded file={f} />,
                  rowExpandable: (f) => isDoctor || !!f.notes.trim(),
                }}
                columns={[
                  {
                    title: 'شرح',
                    dataIndex: 'description',
                    render: (d: string, f) => (
                      <Space>
                        {!f.original_filename && <FileTextOutlined />}
                        {d || (!f.original_filename ? 'بدون شرح' : '')}
                      </Space>
                    ),
                  },
                  {
                    title: 'نام فایل',
                    dataIndex: 'original_filename',
                    render: (name: string | null) =>
                      name ?? (
                        <Typography.Text type="secondary">بدون فایل</Typography.Text>
                      ),
                  },
                  { title: 'حجم', dataIndex: 'size_bytes', render: fileSize },
                  {
                    title: 'وضعیت',
                    dataIndex: 'missing_file',
                    render: (m: boolean) =>
                      m ? <Typography.Text type="danger">مفقود</Typography.Text> : 'موجود',
                  },
                  {
                    title: 'عملیات',
                    render: (_, f) => (
                      <Space>
                        <Button
                          size="small"
                          icon={<DownloadOutlined />}
                          disabled={f.missing_file || !f.original_filename}
                          onClick={() => downloadFile(f.id, f.original_filename)}
                        >
                          دانلود
                        </Button>
                        {isDoctor && (
                          <Popconfirm
                            title="فایل به سبد بازیافت منتقل شود؟"
                            onConfirm={() => delFile.mutate(f.id)}
                          >
                            <Button size="small" danger>
                              حذف
                            </Button>
                          </Popconfirm>
                        )}
                      </Space>
                    ),
                  },
                ]}
              />
            </Space>
          ),
        },
        {
          key: 'txns',
          label: 'پرداخت‌ها',
          children: (
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Row gutter={16}>
                <Col span={8}>
                  <Card>
                    <Statistic
                      title="جمع کل"
                      value={formatMoney(
                        (txns.data?.items ?? []).reduce((s, t) => s + t.amount, 0),
                      )}
                    />
                  </Card>
                </Col>
              </Row>
              <Form
                form={txnForm}
                layout="inline"
                initialValues={{ pos: true }}
                onFinish={(v) =>
                  addTxn.mutate({
                    description: v.description,
                    amount: Number(v.amount),
                    pos: v.pos,
                  })
                }
              >
                <Form.Item name="description" rules={[{ required: true }]}>
                  <AutoComplete
                    options={[{ value: 'ویزیت' }, { value: 'اسپیرو' }]}
                    placeholder="شرح (مثلاً ویزیت)"
                    style={{ width: 180 }}
                  />
                </Form.Item>
                <Form.Item name="amount" rules={[{ required: true }]}>
                  <Input type="number" placeholder="مبلغ" min={0} />
                </Form.Item>
                <Form.Item name="pos" label="روش">
                  <Radio.Group>
                    <Radio.Button value={true}>کارت‌خوان</Radio.Button>
                    <Radio.Button value={false}>نقدی</Radio.Button>
                  </Radio.Group>
                </Form.Item>
                <Button htmlType="submit" loading={addTxn.isPending}>
                  افزودن
                </Button>
              </Form>
              <Table<Transaction>
                rowKey="id"
                dataSource={txns.data?.items ?? []}
                pagination={false}
                size="small"
                columns={[
                  { title: 'شرح', dataIndex: 'description' },
                  { title: 'مبلغ', dataIndex: 'amount', render: formatMoney },
                  {
                    title: 'نوع',
                    dataIndex: 'pos',
                    render: (pos: boolean) => (pos ? 'کارت‌خوان' : 'نقدی'),
                  },
                  {
                    title: '',
                    render: (_, t) => (
                      <Popconfirm
                        title="تراکنش به سبد بازیافت منتقل شود؟"
                        onConfirm={() => delTxn.mutate(t.id)}
                      >
                        <Button size="small" danger>
                          حذف
                        </Button>
                      </Popconfirm>
                    ),
                  },
                ]}
              />
            </Space>
          ),
        },
      ]}
    />
      <Modal
        open={noteFileOpen}
        title="ثبت شرح و یادداشت بدون فایل"
        okText="ثبت"
        cancelText="انصراف"
        onCancel={() => setNoteFileOpen(false)}
        confirmLoading={addNoteFile.isPending}
        onOk={() => noteFileForm.submit()}
        destroyOnHidden
      >
        <Form
          form={noteFileForm}
          layout="vertical"
          onFinish={(v: { description: string; notes: string }) =>
            addNoteFile.mutate({ description: v.description, notes: v.notes ?? '' })
          }
        >
          <Form.Item
            name="description"
            label="شرح"
            rules={[{ required: true, message: 'شرح الزامی است' }]}
          >
            <Input maxLength={128} placeholder="مثلاً گزارش آزمایش" />
          </Form.Item>
          <Form.Item name="notes" label="یادداشت">
            <Input.TextArea rows={3} maxLength={10000} placeholder="اختیاری" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
