import { useEffect } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { App as AntApp, Button, Card, Space, Spin, Statistic, Typography } from 'antd'
import { DownloadOutlined, DeleteOutlined, FileZipOutlined } from '@ant-design/icons'

import { api, apiError } from '../api/client'
import { toFaDigits } from '../lib/jalali'

interface BackupStatus {
  status: 'idle' | 'running' | 'ready' | 'error'
  started_at: string | null
  finished_at: string | null
  error: string | null
  size_bytes: number | null
}

function fileSize(bytes: number | null): string {
  if (bytes == null) return '-'
  if (bytes < 1024 * 1024) return `${toFaDigits((bytes / 1024).toFixed(0))} کیلوبایت`
  return `${toFaDigits((bytes / 1024 / 1024).toFixed(1))} مگابایت`
}

export default function BackupPage() {
  const { message } = AntApp.useApp()

  const status = useQuery({
    queryKey: ['backup-status'],
    queryFn: async () => (await api.get<BackupStatus>('/admin/backup')).data,
  })
  const st = status.data?.status ?? 'idle'

  // poll while a job is in progress
  useEffect(() => {
    if (st !== 'running') return
    const t = setInterval(() => status.refetch(), 2000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [st])

  const start = useMutation({
    mutationFn: async () => api.post('/admin/backup'),
    onSuccess: async () => {
      message.success('ساخت پشتیبان آغاز شد')
      await status.refetch()
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const discard = useMutation({
    mutationFn: async () => api.delete('/admin/backup'),
    onSuccess: async () => {
      message.success('فایل پشتیبان حذف شد')
      await status.refetch()
    },
    onError: (err) => message.error(apiError(err).message),
  })

  const download = async () => {
    try {
      const res = await api.get('/admin/backup/download', { responseType: 'blob' })
      const url = URL.createObjectURL(res.data)
      const link = document.createElement('a')
      link.href = url
      const d = new Date()
      const p = (n: number) => String(n).padStart(2, '0')
      link.download = `clinic-backup-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}.tar.gz`
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      message.error(apiError(err).message)
    }
  }

  return (
    <div>
      <Typography.Title level={3}>پشتیبان‌گیری</Typography.Title>
      <Card>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Space size="large" wrap>
            <Card size="small">
              <Statistic
                title="وضعیت"
                value={
                  st === 'ready'
                    ? 'آماده دانلود'
                    : st === 'running'
                      ? 'در حال آماده‌سازی…'
                      : st === 'error'
                        ? 'خطا'
                        : 'پشتیبانی موجود نیست'
                }
                prefix={st === 'running' ? <Spin size="small" /> : <FileZipOutlined />}
              />
            </Card>
            {st === 'ready' && (
              <Card size="small">
                <Statistic title="حجم فایل" value={fileSize(status.data?.size_bytes ?? null)} />
              </Card>
            )}
          </Space>

          {st === 'error' && (
            <Typography.Text type="danger">
              خطا در ساخت پشتیبان: {status.data?.error}
            </Typography.Text>
          )}

          <Space wrap>
            {st === 'running' ? (
              <Button type="primary" loading disabled>
                در حال آماده‌سازی…
              </Button>
            ) : (
              <Button
                type="primary"
                icon={<FileZipOutlined />}
                loading={status.isLoading}
                onClick={() => start.mutate()}
              >
                ساخت پشتیبان
              </Button>
            )}
            {st === 'ready' && (
              <>
                <Button type="primary" icon={<DownloadOutlined />} onClick={download}>
                  دانلود پشتیبان
                </Button>
                <Button danger icon={<DeleteOutlined />} onClick={() => discard.mutate()}>
                  حذف فایل
                </Button>
              </>
            )}
          </Space>

          <Typography.Text type="secondary">
            فایل پشتیبان شامل کل پایگاه داده (SQL) و فایل‌های بارگذاری‌شده است. پس از اتمام، لینک
            دانلود در همین صفحه فعال می‌شود.
          </Typography.Text>
        </Space>
      </Card>
    </div>
  )
}
