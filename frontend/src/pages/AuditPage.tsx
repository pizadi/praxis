import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, Select, Table, Tag, Typography } from 'antd'

import { api } from '../api/client'
import type { Page } from '../api/types'
import { formatJalali } from '../lib/jalali'

interface AuditEntry {
  id: number
  user_id: number | null
  username: string
  action: string
  entity_type: string
  entity_id: number | null
  summary: string
  details: string | null
  ip_address: string
  created_at: string
}

const ACTION_LABELS: Record<string, { label: string; color: string }> = {
  create: { label: 'ایجاد', color: 'green' },
  update: { label: 'ویرایش', color: 'blue' },
  delete: { label: 'حذف', color: 'red' },
  restore: { label: 'بازیابی', color: 'orange' },
  purge: { label: 'حذف قطعی', color: 'magenta' },
}

const ENTITY_LABELS: Record<string, string> = {
  patient: 'بیمار',
  appointment: 'نوبت',
  file: 'فایل',
  transaction: 'تراکنش',
  tag: 'برچسب',
  diagnosi: 'تشخیص',
  user: 'کاربر',
}

export default function AuditPage() {
  const [page, setPage] = useState(1)
  const [action, setAction] = useState<string | null>(null)
  const [entityType, setEntityType] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['audit', page, action, entityType],
    queryFn: async () =>
      (await api.get<Page<AuditEntry>>('/admin/audit', {
        params: {
          action: action ?? undefined,
          entity_type: entityType ?? undefined,
          limit: 50,
          offset: (page - 1) * 50,
        },
      })).data,
  })

  return (
    <div>
      <Typography.Title level={3}>گزارش اقدامات</Typography.Title>
      <Typography.Paragraph type="secondary">
        همه عملیات‌های ایجاد، ویرایش، حذف، بازیابی و حذف قطعی به همراه کاربر، زمان و
        نشانی IP ثبت می‌شوند.
      </Typography.Paragraph>
      <Card>
        <div style={{ marginBottom: 16, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Select
            allowClear
            placeholder="نوع عملیات"
            style={{ width: 150 }}
            value={action}
            onChange={(v) => {
              setAction(v ?? null)
              setPage(1)
            }}
            options={Object.entries(ACTION_LABELS).map(([k, v]) => ({
              value: k,
              label: v.label,
            }))}
          />
          <Select
            allowClear
            placeholder="نوع موجودیت"
            style={{ width: 150 }}
            value={entityType}
            onChange={(v) => {
              setEntityType(v ?? null)
              setPage(1)
            }}
            options={Object.entries(ENTITY_LABELS).map(([k, v]) => ({
              value: k,
              label: v,
            }))}
          />
        </div>
        <Table<AuditEntry>
          rowKey="id"
          loading={isLoading}
          dataSource={data?.items ?? []}
          pagination={{
            current: page,
            pageSize: 50,
            total: data?.total ?? 0,
            onChange: setPage,
          }}
          columns={[
            {
              title: 'زمان',
              dataIndex: 'created_at',
              render: (v: string) => formatJalali(v, true),
            },
            { title: 'کاربر', dataIndex: 'username' },
            {
              title: 'عملیات',
              dataIndex: 'action',
              render: (a: string) => (
                <Tag color={ACTION_LABELS[a]?.color ?? 'default'}>
                  {ACTION_LABELS[a]?.label ?? a}
                </Tag>
              ),
            },
            {
              title: 'موجودیت',
              dataIndex: 'entity_type',
              render: (t: string, row) =>
                `${ENTITY_LABELS[t] ?? t} #${row.entity_id ?? '—'}`,
            },
            { title: 'شرح', dataIndex: 'summary' },
            {
              title: 'جزئیات',
              dataIndex: 'details',
              render: (d: string | null) =>
                d ? (
                  <Typography.Text code style={{ fontSize: 11 }}>
                    {d.length > 80 ? d.slice(0, 80) + '…' : d}
                  </Typography.Text>
                ) : (
                  '—'
                ),
            },
            {
              title: 'IP',
              dataIndex: 'ip_address',
              render: (v: string) => (v ? <Typography.Text type="secondary">{v}</Typography.Text> : '—'),
            },
          ]}
        />
      </Card>
    </div>
  )
}
