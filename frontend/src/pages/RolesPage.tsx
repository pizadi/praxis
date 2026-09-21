import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntApp,
  Button,
  Card,
  Checkbox,
  Divider,
  Form,
  Input,
  Modal,
  Popconfirm,
  Space,
  Table,
  Tag,
  Typography,
  theme as antdTheme,
} from 'antd'

import { api, apiError } from '../api/client'
import type { Page, PermissionGroup, Role } from '../api/types'

interface RoleForm {
  name: string
  permissions: string[]
}

export default function RolesPage() {
  const { message } = AntApp.useApp()
  const qc = useQueryClient()
  const [form] = Form.useForm<RoleForm>()
  const [editing, setEditing] = useState<Role | null>(null)
  const [open, setOpen] = useState(false)

  const roles = useQuery({
    queryKey: ['roles'],
    queryFn: async () => (await api.get<Page<Role>>('/roles', { params: { limit: 100 } })).data,
  })

  const catalog = useQuery({
    queryKey: ['permission-catalog'],
    queryFn: async () => (await api.get<PermissionGroup[]>('/roles/permissions')).data,
  })

  const save = useMutation({
    mutationFn: async (values: RoleForm) => {
      if (editing) return api.patch(`/roles/${editing.id}`, values)
      return api.post('/roles', values)
    },
    onSuccess: () => {
      message.success('ذخیره شد')
      setOpen(false)
      setEditing(null)
      form.resetFields()
      qc.invalidateQueries({ queryKey: ['roles'] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const remove = useMutation({
    mutationFn: async (id: number) => api.delete(`/roles/${id}`),
    onSuccess: () => {
      message.success('حذف شد')
      qc.invalidateQueries({ queryKey: ['roles'] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const openEdit = (r: Role | null) => {
    setEditing(r)
    form.setFieldsValue({
      name: r?.name ?? '',
      permissions: r?.permissions ?? [],
    })
    setOpen(true)
  }

  return (
    <div>
      <Typography.Title level={3}>نقش‌ها و دسترسی‌ها</Typography.Title>
      <Card
        extra={
          <Button type="primary" onClick={() => openEdit(null)}>
            نقش جدید
          </Button>
        }
      >
        <Table<Role>
          rowKey="id"
          loading={roles.isLoading}
          dataSource={roles.data?.items ?? []}
          pagination={false}
          expandable={{
            expandedRowRender: (r) => (
              <Typography.Paragraph style={{ margin: 0 }}>
                {(r.permissions ?? []).length === 0 ? (
                  <Typography.Text type="secondary">بدون دسترسی</Typography.Text>
                ) : (
                  [...(r.permissions ?? [])]
                    .sort()
                    .map((p) => (
                      <Tag key={p} style={{ marginInlineEnd: 4, marginBlock: 2 }}>
                        {p}
                      </Tag>
                    ))
                )}
              </Typography.Paragraph>
            ),
          }}
          columns={[
            { title: 'نام نقش', dataIndex: 'name' },
            {
              title: 'تعداد دسترسی‌ها',
              render: (_, r) => (r.permissions ?? []).length,
            },
            { title: 'کاربران', dataIndex: 'user_count' },
            {
              title: 'عملیات',
              render: (_, r) => {
                const isAdminRole = r.is_system && r.name === 'admin'
                return (
                  <Space>
                    <Button
                      size="small"
                      disabled={isAdminRole}
                      title={isAdminRole ? 'نقش مدیر قابل ویرایش نیست' : undefined}
                      onClick={() => openEdit(r)}
                    >
                      ویرایش
                    </Button>
                    {!r.is_system && (
                      <Popconfirm title="این نقش حذف شود؟" onConfirm={() => remove.mutate(r.id)}>
                        <Button size="small" danger disabled={(r.user_count ?? 0) > 0}>
                          حذف
                        </Button>
                      </Popconfirm>
                    )}
                  </Space>
                )
              },
            },
          ]}
        />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          نقش «مدیر» همیشه به همه دسترسی‌ها دارد و قابل ویرایش نیست.
        </Typography.Text>
      </Card>

      <Modal
        open={open}
        title={editing ? `ویرایش نقش: ${editing.name}` : 'نقش جدید'}
        maskClosable={false}
        onCancel={() => {
          setOpen(false)
          setEditing(null)
        }}
        onOk={() => form.submit()}
        confirmLoading={save.isPending}
        width={720}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
          <Form.Item
            name="name"
            label="نام نقش"
            rules={[{ required: true, message: 'نام نقش الزامی است' }]}
          >
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item name="permissions" label="دسترسی‌ها">
            <PermissionCheckboxes groups={catalog.data ?? []} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

/** Form-bound permission grid. antd Form.Item injects `value` (the role's
 * active permission keys) and `onChange` into its direct child — forward
 * them into a Checkbox.Group so existing permissions show as checked and
 * checking boxes updates the form field. */
function PermissionCheckboxes({
  groups,
  value,
  onChange,
}: {
  groups: PermissionGroup[]
  value?: string[]
  onChange?: (values: string[]) => void
}) {
  const { token } = antdTheme.useToken()
  if (groups.length === 0) return null
  return (
    <Checkbox.Group
      value={value}
      onChange={(v) => onChange?.(v as string[])}
      style={{ display: 'block' }}
    >
      <div style={{ maxHeight: 360, overflowY: 'auto' }}>
        {groups.map((g, i) => (
          <div key={g.group}>
            {i > 0 && <Divider style={{ margin: '8px 0' }} />}
            <Typography.Text strong>{g.group}</Typography.Text>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 4 }}>
              {g.items.map((item) => (
                <Checkbox key={item.key} value={item.key} style={{ marginInlineStart: 0 }}>
                  {item.label}
                  <Typography.Text type="secondary" style={{ fontSize: 11, marginInlineStart: 4 }}>
                    {item.key}
                  </Typography.Text>
                </Checkbox>
              ))}
            </div>
          </div>
        ))}
        <div
          style={{
            background: token.colorFillQuaternary,
            padding: 8,
            marginTop: 8,
            borderRadius: 4,
          }}
        >
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            تغییر دسترسی‌ها بلافاصله برای همه کاربران این نقش اعمال می‌شود.
          </Typography.Text>
        </div>
      </div>
    </Checkbox.Group>
  )
}
