import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntApp,
  Button,
  Card,
  Popconfirm,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'

import { api, apiError } from '../api/client'
import type { Page } from '../api/types'
import { formatJalali } from '../lib/jalali'
import { useIsMobile } from '../lib/useIsMobile'
import { useUser } from '../components/AppLayout'
import StackCell from '../components/StackCell'

export interface TrashItem {
  id: number
  type: string
  deleted_at: string
  title: string
  subtitle: string
  parent_deleted: boolean
}

const TYPE_LABELS: Record<string, string> = {
  patients: 'بیماران',
  appointments: 'نوبت‌ها',
  transactions: 'تراکنش‌ها',
  attachments: 'فایل‌ها',
  tags: 'برچسب‌ها',
  diagnoses: 'تشخیص‌ها',
  users: 'کاربران',
  roles: 'نقش‌ها',
  questionnaire_templates: 'قالب پرسش‌نامه‌ها',
  questionnaire_responses: 'پاسخ‌های پرسش‌نامه',
}

function TrashTable({
  type,
  canPurge,
}: {
  type: string
  canPurge: boolean
}) {
  const { message } = AntApp.useApp()
  const qc = useQueryClient()
  const isMobile = useIsMobile()
  const [page, setPage] = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['trash', type, page],
    queryFn: async () =>
      (await api.get<Page<TrashItem>>(`/admin/trash/${type}`, {
        params: { limit: 20, offset: (page - 1) * 20 },
      })).data,
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['trash', type] })
    // restoring may reveal items elsewhere in the app
    qc.invalidateQueries({ queryKey: ['patients'] })
    qc.invalidateQueries({ queryKey: ['appointments'] })
    qc.invalidateQueries({ queryKey: ['tags'] })
    qc.invalidateQueries({ queryKey: ['diagnoses'] })
    qc.invalidateQueries({ queryKey: ['users'] })
  }

  const restore = useMutation({
    mutationFn: async (id: number) =>
      api.post(`/admin/trash/${type}/${id}/restore`),
    onSuccess: () => {
      message.success('بازگردانی شد')
      invalidate()
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const purge = useMutation({
    mutationFn: async (id: number) => api.delete(`/admin/trash/${type}/${id}`),
    onSuccess: () => {
      message.success('برای همیشه حذف شد')
      invalidate()
    },
    onError: (err) => message.error(apiError(err).message),
  })

  return (
    <Table<TrashItem>
      rowKey="id"
      loading={isLoading}
      dataSource={data?.items ?? []}
      scroll={isMobile ? undefined : { x: 'max-content' }}
      pagination={{
        current: page,
        pageSize: 20,
        total: data?.total ?? 0,
        onChange: setPage,
      }}
      locale={{ emptyText: 'موردی در سبد بازیافت نیست' }}
      columns={
        isMobile
          ? [
              {
                title: 'عنوان',
                render: (_, item) => (
                  <StackCell
                    main={item.title}
                    lines={[
                      item.subtitle || null,
                      formatJalali(item.deleted_at, true),
                      item.parent_deleted ? (
                        <Tag color="orange">والد هم حذف است</Tag>
                      ) : (
                        <Tag color="green">قابل بازیابی</Tag>
                      ),
                    ]}
                  />
                ),
              },
              {
                title: 'عملیات',
                render: (_, item) => (
                  <Space direction="vertical">
                    <Button
                      size="small"
                      type="primary"
                      loading={restore.isPending && restore.variables === item.id}
                      onClick={() => restore.mutate(item.id)}
                    >
                      بازیابی
                    </Button>
                    {canPurge && (
                      <Popconfirm
                        title="برای همیشه حذف شود؟ این عمل قابل بازگشت نیست."
                        onConfirm={() => purge.mutate(item.id)}
                      >
                        <Button size="small" danger>
                          حذف قطعی
                        </Button>
                      </Popconfirm>
                    )}
                  </Space>
                ),
              },
            ]
          : [
              { title: 'عنوان', dataIndex: 'title' },
              { title: 'جزئیات', dataIndex: 'subtitle', render: (v: string) => v || '—' },
              {
                title: 'زمان حذف',
                dataIndex: 'deleted_at',
                render: (v: string) => formatJalali(v, true),
              },
              {
                title: 'وضعیت',
                render: (_, item) =>
                  item.parent_deleted ? (
                    <Tag color="orange">والد هم حذف است</Tag>
                  ) : (
                    <Tag color="green">قابل بازیابی</Tag>
                  ),
              },
              {
                title: 'عملیات',
                render: (_, item) => (
                  <Space>
                    <Button
                      size="small"
                      type="primary"
                      loading={restore.isPending && restore.variables === item.id}
                      onClick={() => restore.mutate(item.id)}
                    >
                      بازیابی
                    </Button>
                    {canPurge && (
                      <Popconfirm
                        title="برای همیشه حذف شود؟ این عمل قابل بازگشت نیست."
                        onConfirm={() => purge.mutate(item.id)}
                      >
                        <Button size="small" danger>
                          حذف قطعی
                        </Button>
                      </Popconfirm>
                    )}
                  </Space>
                ),
              },
            ]
      }
    />
  )
}

export default function TrashPage() {
  const { hasPerm } = useUser()
  const canPurge = hasPerm('trash.purge')

  const types = canPurge
    ? Object.keys(TYPE_LABELS)
    : ['patients', 'appointments', 'transactions', 'attachments', 'tags', 'diagnoses']

  return (
    <div>
      <Typography.Title level={3}>سبد بازیافت</Typography.Title>
      <Typography.Paragraph type="secondary">
        موارد حذف‌شده اینجا نمایش داده می‌شوند و تا حذف قطعی قابل بازگردانی هستند.
        {canPurge && ' حذف قطعی فقط برای مدیر فعال است و فایل‌های فیزیکی را پاک می‌کند.'}
      </Typography.Paragraph>
      <Card>
        <Tabs
          items={types.map((t) => ({
            key: t,
            label: TYPE_LABELS[t],
            children: <TrashTable type={t} canPurge={canPurge} />,
          }))}
        />
      </Card>
    </div>
  )
}
