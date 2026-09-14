import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntApp,
  Button,
  Card,
  Col,
  Input,
  List,
  Popconfirm,
  Row,
  Space,
  Tag,
  Typography,
} from 'antd'

import { api, apiError } from '../api/client'
import type { NamedRef } from '../api/types'
import { useUser } from '../components/AppLayout'

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

  const items = useQuery({
    queryKey: [kind],
    queryFn: async () => (await api.get<NamedRef[]>(`/${kind}`)).data,
  })

  const create = useMutation({
    mutationFn: async () => api.post(`/${kind}`, { name }),
    onSuccess: () => {
      message.success('افزوده شد')
      setName('')
      qc.invalidateQueries({ queryKey: [kind] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const rename = useMutation({
    mutationFn: async ({ id, newName }: { id: number; newName: string }) =>
      api.patch(`/${kind}/${id}`, { name: newName }),
    onSuccess: () => {
      message.success('تغییر نام انجام شد')
      qc.invalidateQueries({ queryKey: [kind] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const remove = useMutation({
    mutationFn: async (id: number) => api.delete(`/${kind}/${id}`),
    onSuccess: () => {
      message.success('حذف شد')
      qc.invalidateQueries({ queryKey: [kind] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  return (
    <Card title={title}>
      {canEdit && (
        <Space.Compact style={{ marginBottom: 16 }}>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="نام جدید…"
            onPressEnter={() => name.trim() && create.mutate()}
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
      <List
        loading={items.isLoading}
        dataSource={items.data ?? []}
        locale={{ emptyText: 'خالی است' }}
        renderItem={(item) => (
          <List.Item
            actions={
              canEdit
                ? [
                    <Button
                      key="rename"
                      size="small"
                      onClick={() => {
                        const newName = window.prompt('نام جدید:', item.name)
                        if (newName && newName.trim() && newName !== item.name) {
                          rename.mutate({ id: item.id, newName: newName.trim() })
                        }
                      }}
                    >
                      تغییر نام
                    </Button>,
                    <Popconfirm
                      key="del"
                      title="حذف شود؟ (از پرونده همه بیماران حذف می‌شود)"
                      onConfirm={() => remove.mutate(item.id)}
                    >
                      <Button size="small" danger>
                        حذف
                      </Button>
                    </Popconfirm>,
                  ]
                : undefined
            }
          >
            <Tag color={color}>{item.name}</Tag>
          </List.Item>
        )}
      />
    </Card>
  )
}

export default function TaxonomiesPage() {
  const { isDoctor } = useUser()
  return (
    <div>
      <Typography.Title level={3}>برچسب‌ها و تشخیص‌ها</Typography.Title>
      <Row gutter={16}>
        <Col span={12}>
          <TaxonomyPanel kind="tags" title="برچسب‌ها" color="blue" canEdit={isDoctor} />
        </Col>
        <Col span={12}>
          <TaxonomyPanel kind="diagnoses" title="تشخیص‌ها" color="red" canEdit={isDoctor} />
        </Col>
      </Row>
    </div>
  )
}
