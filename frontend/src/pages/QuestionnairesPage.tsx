import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntApp,
  Button,
  Card,
  Form,
  Modal,
  Popconfirm,
  Space,
  Table,
  Typography,
  Upload,
} from 'antd'
import type { UploadFile } from 'antd'
import {
  CloudUploadOutlined,
  DeleteOutlined,
  DownloadOutlined,
  PlusOutlined,
} from '@ant-design/icons'

import { api, apiError } from '../api/client'
import type { Page, QuestionnaireTemplate } from '../api/types'
import { toFaDigits } from '../lib/jalali'
import type { FormatDoc } from '../lib/questionnaire'
import { useIsMobile } from '../lib/useIsMobile'
import StackCell from '../components/StackCell'
import QuestionnaireBuilderForm, {
  builderToFormat,
  formatToBuilder,
  type BuilderState,
} from '../components/questionnaires/QuestionnaireBuilderForm'

/** Example JSON users can download as a starting point for uploads. */
const EXAMPLE_FORMAT: FormatDoc = {
  version: 1,
  title: 'پرسش‌نامه نمونه',
  score_formula: 'pain_level + mobility',
  questions: [
    {
      key: 'pain',
      label: 'شدت درد (۰ تا ۱۰)',
      type: 'number',
      required: true,
      min: 0,
      max: 10,
      integer: true,
      unit: '',
    },
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
    {
      key: 'notes',
      label: 'توضیحات',
      type: 'string',
      required: false,
      multiline: true,
      max_length: 500,
    },
  ],
}

export default function QuestionnairesPage() {
  const { message } = AntApp.useApp()
  const queryClient = useQueryClient()
  const isMobile = useIsMobile()
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
      const format = builderToFormat(values)
      const body = { name: values.name, description: values.description, format }
      if (editing) return api.patch(`/questionnaires/templates/${editing.id}`, body)
      return api.post('/questionnaires/templates', body)
    },
    onSuccess: async () => {
      message.success('ذخیره شد')
      setOpen(false)
      setEditing(null)
      form.resetFields()
      setUploadList([])
      await queryClient.invalidateQueries({ queryKey: ['questionnaire-templates'] })
    },
    onError: (error) => message.error(apiError(error).message),
  })

  const remove = useMutation({
    mutationFn: async (id: number) => api.delete(`/questionnaires/templates/${id}`),
    onSuccess: async () => {
      message.success('به سبد بازیافت منتقل شد')
      await queryClient.invalidateQueries({ queryKey: ['questionnaire-templates'] })
    },
    onError: (error) => message.error(apiError(error).message),
  })

  /** Upload a JSON file: parsed client-side, validated by the server
   * endpoint, then loaded into the graphical builder for review. */
  const loadFromJson = async (file: File) => {
    try {
      const text = await file.text()
      const parsed = JSON.parse(text) as Record<string, unknown>
      const check = await api.post('/questionnaires/templates/validate', {
        name: (parsed.title as string) || file.name.replace(/\.json$/i, ''),
        description: '',
        format: parsed,
      })
      const format = check.data.format as FormatDoc
      const state = formatToBuilder(format)
      form.setFieldsValue({
        ...state,
        name: form.getFieldValue('name') || check.data.name,
      })
      setUploadList([])
      setEditing(null)
      setOpen(true)
      message.success('فایل معتبر است و در فرم بارگذاری شد — بررسی و ذخیره کنید')
    } catch (error) {
      message.error(apiError(error).message)
    }
    return false
  }

  const openEdit = (template: QuestionnaireTemplate | null) => {
    setEditing(template)
    setUploadList([])
    if (template) {
      form.setFieldsValue(
        formatToBuilder(
          template.format as FormatDoc,
          template.name,
          template.description,
        ),
      )
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
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = 'questionnaire-example.json'
    anchor.click()
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
          scroll={isMobile ? undefined : { x: 'max-content' }}
          columns={
            isMobile
              ? [
                  {
                    title: 'قالب',
                    render: (_, template) => (
                      <StackCell
                        main={template.name}
                        lines={[
                          template.description || null,
                          `${toFaDigits((template.format?.questions ?? []).length)} پرسش`,
                        ]}
                      />
                    ),
                  },
                  {
                    title: 'عملیات',
                    render: (_, template) => (
                      <Space>
                        <Button size="small" onClick={() => openEdit(template)}>
                          ویرایش
                        </Button>
                        <Popconfirm
                          title="قالب به سبد بازیافت منتقل شود؟"
                          onConfirm={() => remove.mutate(template.id)}
                        >
                          <Button size="small" danger icon={<DeleteOutlined />} />
                        </Popconfirm>
                      </Space>
                    ),
                  },
                ]
              : [
                  { title: 'نام', dataIndex: 'name' },
                  { title: 'توضیح', dataIndex: 'description' },
                  {
                    title: 'تعداد پرسش‌ها',
                    render: (_, template) => (template.format?.questions ?? []).length,
                  },
                  {
                    title: 'عملیات',
                    render: (_, template) => (
                      <Space>
                        <Button size="small" onClick={() => openEdit(template)}>
                          ویرایش
                        </Button>
                        <Popconfirm
                          title="قالب به سبد بازیافت منتقل شود؟"
                          onConfirm={() => remove.mutate(template.id)}
                        >
                          <Button size="small" danger icon={<DeleteOutlined />} />
                        </Popconfirm>
                      </Space>
                    ),
                  },
                ]
          }
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
        width="min(96vw, 860px)"
        destroyOnHidden
      >
        <QuestionnaireBuilderForm form={form} onFinish={(values) => save.mutate(values)} />
      </Modal>
    </div>
  )
}
