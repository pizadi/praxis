import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntApp,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Switch,
  Table,
  Typography,
} from 'antd'

import { api, apiError } from '../api/client'
import { roleFa } from '../lib/roles'
import type { Page, Role, User } from '../api/types'

interface UserForm {
  username: string
  password?: string
  full_name?: string
  role_id: number
  is_active?: boolean
}

export default function UsersPage() {
  const { message } = AntApp.useApp()
  const qc = useQueryClient()
  const [form] = Form.useForm<UserForm>()
  const [editing, setEditing] = useState<User | null>(null)
  const [open, setOpen] = useState(false)

  const users = useQuery({
    queryKey: ['users'],
    queryFn: async () => (await api.get<Page<User>>('/users', { params: { limit: 100 } })).data,
  })

  const roles = useQuery({
    queryKey: ['roles'],
    queryFn: async () => (await api.get<Page<Role>>('/roles', { params: { limit: 100 } })).data,
  })

  const save = useMutation({
    mutationFn: async (values: UserForm) => {
      if (editing) {
        const { password, ...rest } = values
        return api.patch(`/users/${editing.id}`, {
          ...rest,
          ...(password ? { password } : {}),
        })
      }
      return api.post('/users', values)
    },
    onSuccess: () => {
      message.success('ذخیره شد')
      setOpen(false)
      setEditing(null)
      form.resetFields()
      qc.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const remove = useMutation({
    mutationFn: async (id: number) => api.delete(`/users/${id}`),
    onSuccess: () => {
      message.success('حذف شد')
      qc.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (err) => message.error(apiError(err).message),
  })


  return (
    <div>
      <Typography.Title level={3}>کاربران</Typography.Title>
      <Card
        extra={
          <Button
            type="primary"
            onClick={() => {
              setEditing(null)
              form.resetFields()
              setOpen(true)
            }}
          >
            کاربر جدید
          </Button>
        }
      >
        <Table<User>
          rowKey="id"
          loading={users.isLoading}
          dataSource={users.data?.items ?? []}
          pagination={false}
          columns={[
            { title: 'نام کاربری', dataIndex: 'username' },
            { title: 'نام کامل', dataIndex: 'full_name' },
            {
              title: 'نقش',
              dataIndex: 'role_name',
              render: (v: string) => roleFa(v),
            },
            {
              title: 'فعال',
              dataIndex: 'is_active',
              render: (v: boolean) => (v ? 'بله' : 'خیر'),
            },
            {
              title: 'عملیات',
              render: (_, u) => (
                <>
                  <Button
                    size="small"
                    style={{ marginInlineEnd: 8 }}
                    onClick={() => {
                      setEditing(u)
                      form.setFieldsValue({
                        username: u.username,
                        full_name: u.full_name,
                        role_id: u.role_id,
                        is_active: u.is_active,
                      })
                      setOpen(true)
                    }}
                  >
                    ویرایش
                  </Button>
                  <Popconfirm title="حذف کاربر؟" onConfirm={() => remove.mutate(u.id)}>
                    <Button size="small" danger>
                      حذف
                    </Button>
                  </Popconfirm>
                </>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        open={open}
        title={editing ? 'ویرایش کاربر' : 'کاربر جدید'}
        maskClosable={false}
        onCancel={() => {
          setOpen(false)
          setEditing(null)
        }}
        onOk={() => form.submit()}
        confirmLoading={save.isPending}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
          {!editing && (
            <Form.Item
              name="username"
              label="نام کاربری"
              rules={[
                { required: true },
                { pattern: /^[a-zA-Z0-9_.-]+$/, message: 'فقط حروف/رقم انگلیسی' },
              ]}
            >
              <Input />
            </Form.Item>
          )}
          <Form.Item
            name="password"
            label="گذرواژه"
            rules={editing ? [] : [{ required: true }, { min: 8, message: 'حداقل ۸ نویسه' }]}
          >
            <Input.Password placeholder={editing ? 'برای تغییر وارد کنید' : ''} />
          </Form.Item>
          <Form.Item name="full_name" label="نام کامل">
            <Input />
          </Form.Item>
          <Form.Item name="role_id" label="نقش" rules={[{ required: true }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={(roles.data?.items ?? []).map((r) => ({
                value: r.id,
                label: r.name,
              }))}
            />
          </Form.Item>
          {editing && (
            <Form.Item name="is_active" label="فعال" valuePropName="checked">
              <Switch />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  )
}
