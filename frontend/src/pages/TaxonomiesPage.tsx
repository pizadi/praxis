import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntApp,
  Button,
  Card,
  Col,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'

import { api, apiError } from '../api/client'
import type { NamedRef, Page } from '../api/types'
import { toFaDigits } from '../lib/jalali'
import { useUser } from '../components/AppLayout'

const PAGE_SIZE = 20

function TaxonomyPanel({
  kind,
  title,
  color,
  canEdit,
}: {
  kind: 'tags' | 'diagnoses'
  title: string
  color: string
  canEdit: boolean
}) {
  const { message } = AntApp.useApp()
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [renaming, setRenaming] = useState<NamedRef | null>(null)
  const [renameForm] = Form.useForm<{ name: string }>()

  const items = useQuery({
    queryKey: [kind, search, (page - 1) * PAGE_SIZE],
    queryFn: async () =>
      (await api.get<Page<NamedRef>>(`/${kind}`, {
        params: { q: search || undefined, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE },
      })).data,
  })

  const create = useMutation({
    mutationFn: async () => api.post(`/${kind}`, { name }),
    onSuccess: async () => {
      message.success('افزوده شد')
      setName('')
      setPage(1)
      await qc.invalidateQueries({ queryKey: [kind] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const rename = useMutation({
    mutationFn: async ({ id, newName }: { id: number; newName: string }) =>
      api.patch(`/${kind}/${id}`, { name: newName }),
    onSuccess: async () => {
      message.success('تغییر نام انجام شد')
      setRenaming(null)
      await qc.invalidateQueries({ queryKey: [kind] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const remove = useMutation({
    mutationFn: async (id: number) => api.delete(`/${kind}/${id}`),
    onSuccess: async () => {
      message.success('حذف شد')
      await qc.invalidateQueries({ queryKey: [kind] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const columns: ColumnsType<NamedRef> = [
    {
      title: 'نام',
      dataIndex: 'name',
      render: (n: string) => <Tag color={color}>{n}</Tag>,
    },
    {
      title: 'عملیات',
      width: 170,
      render: (_, item) =>
        canEdit ? (
          <Space>
            <Button
              size="small"
              onClick={() => {
                setRenaming(item)
                renameForm.setFieldsValue({ name: item.name })
              }}
            >
              تغییر نام
            </Button>
            <Popconfirm
              title="حذف شود؟ (از پرونده همه بیماران حذف می‌شود)"
              onConfirm={() => remove.mutate(item.id)}
            >
              <Button size="small" danger>
                حذف
              </Button>
            </Popconfirm>
          </Space>
        ) : undefined,
    },
  ]

  return (
    <Card
      title={title}
      extra={
        <Input.Search
          allowClear
          placeholder="جستجو…"
          style={{ width: 180 }}
          onSearch={(v) => {
            setSearch(v.trim())
            setPage(1)
          }}
        />
      }
    >
      {canEdit && (
        <Space.Compact style={{ marginBottom: 16 }}>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            onPressEnter={() => name.trim() && create.mutate()}
            placeholder="نام جدید…"
          />
          <Button
            type="primary"
            disabled={!name.trim()}
            loading={create.isPending}
            onClick={() => create.mutate()}
          >
            افزودن
          </Button>
        </Space.Compact>
      )}
      <Table<NamedRef>
        rowKey="id"
        size="small"
        loading={items.isFetching}
        dataSource={items.data?.items ?? []}
        columns={columns}
        locale={{ emptyText: 'خالی است' }}
        pagination={{
          total: items.data?.total ?? 0,
          pageSize: PAGE_SIZE,
          current: page,
          showSizeChanger: false,
          showTotal: (t) => `${toFaDigits(t)} مورد`,
          onChange: (p) => setPage(p),
        }}
      />

      <Modal
        open={renaming != null}
        title={`تغییر نام: ${renaming?.name ?? ''}`}
        okText="ذخیره"
        cancelText="انصراف"
        maskClosable={false}
        onCancel={() => setRenaming(null)}
        confirmLoading={rename.isPending}
        onOk={() => renameForm.submit()}
        destroyOnHidden
      >
        <Form
          form={renameForm}
          layout="vertical"
          onFinish={(v) => {
            const newName = v.name?.trim()
            if (renaming && newName && newName !== renaming.name) {
              rename.mutate({ id: renaming.id, newName })
            } else {
              setRenaming(null)
            }
          }}
        >
          <Form.Item name="name" rules={[{ required: true, message: 'نام الزامی است' }]}>
            <Input maxLength={128} autoFocus />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}

export default function TaxonomiesPage() {
  const { hasPerm } = useUser()
  return (
    <div>
      <Typography.Title level={3}>برچسب‌ها و تشخیص‌ها</Typography.Title>
      <Row gutter={16}>
        <Col span={12}>
          <TaxonomyPanel kind="tags" title="برچسب‌ها" color="blue" canEdit={hasPerm('taxonomies.write')} />
        </Col>
        <Col span={12}>
          <TaxonomyPanel kind="diagnoses" title="تشخیص‌ها" color="red" canEdit={hasPerm('taxonomies.write')} />
        </Col>
      </Row>
    </div>
  )
}
