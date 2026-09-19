import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Space,
  Spin,
  Statistic,
  Typography,
  Upload,
} from 'antd'
import {
  CloudUploadOutlined,
  DownloadOutlined,
  DeleteOutlined,
  FileZipOutlined,
} from '@ant-design/icons'
import type { RcFile } from 'antd/es/upload'

import { api, apiError } from '../api/client'
import { toFaDigits } from '../lib/jalali'

interface BackupStatus {
  status: 'idle' | 'running' | 'ready' | 'error'
  started_at: string | null
  finished_at: string | null
  error: string | null
  size_bytes: number | null
}

interface ImportSummary {
  tables: Record<string, number>
  uploads_moved: number
  schema_version: number
}

interface ImportStatus {
  status: 'idle' | 'importing' | 'done' | 'error'
  error: string | null
  summary: ImportSummary | null
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

  // --- import (restore from a tarball) ---
  const { modal } = AntApp.useApp()
  const [importFile, setImportFile] = useState<RcFile | null>(null)
  const lastPicked = useRef<RcFile | null>(null)

  const importStatus = useQuery({
    queryKey: ['backup-import-status'],
    queryFn: async () => (await api.get<ImportStatus>('/admin/backup/import')).data,
  })
  const ist = importStatus.data?.status ?? 'idle'

  useEffect(() => {
    if (ist !== 'importing') return
    const t = setInterval(() => importStatus.refetch(), 2000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ist])

  const doImport = async (f: RcFile, force: boolean) => {
    const fd = new FormData()
    fd.append('file', f)
    fd.append('force', force ? 'true' : 'false')
    try {
      await api.post('/admin/backup/import', fd)
      message.success('واردسازی آغاز شد')
      await importStatus.refetch()
    } catch (err) {
      const e = apiError(err)
      if (e.code === 'newer_version') {
        const d = (e.details ?? {}) as {
          tarball_app_version?: string
          current_app_version?: string
        }
        modal.confirm({
          title: 'نسخهٔ پشتیبان جدیدتر از سامانه است',
          content:
            `نسخهٔ فایل پشتیبان: ${d.tarball_app_version ?? '؟'} — ` +
            `نسخهٔ سامانه: ${d.current_app_version ?? '؟'}. ` +
            'واردسازی ممکن است با خطا مواجه شود؛ در صورت بروز خطای بازگشت‌ناپذیر، همه‌چیز به حالت قبل برمی‌گردد.',
          okText: 'واردسازی به هر حال',
          cancelText: 'انصراف',
          onOk: () => {
            const f2 = lastPicked.current
            if (f2) void doImport(f2, true)
          },
        })
      } else {
        message.error(e.message)
      }
    }
  }

  const pickImport = (f: RcFile) => {
    lastPicked.current = f
    setImportFile(f)
    void doImport(f, false)
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

      <Card
        title="واردسازی پشتیبان"
        style={{ marginTop: 16 }}
        extra={
          <Upload
            accept=".tar.gz,.tgz,application/gzip"
            maxCount={1}
            showUploadList={false}
            disabled={ist === 'importing'}
            beforeUpload={(f) => {
              pickImport(f)
              return false // POST via the axios client, with confirm-flow support
            }}
          >
            <Button icon={<CloudUploadOutlined />} loading={ist === 'importing'}>
              انتخاب فایل پشتیبان…
            </Button>
          </Upload>
        }
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            پروندهٔ پشتیبان (tar.gz) داده‌های فعلی را جایگزین می‌کند: پایگاه داده و
            فایل‌های بارگذاری‌شده به حالت زمان ساخت پشتیبان برمی‌گردند. پشتیبان‌های
            نسخه‌های قدیمی‌تر پذیرفته می‌شوند؛ پشتیبانِ ساخته‌شده با نسخهٔ جدیدتر
            سامانه، پیش از واردسازی تأیید جداگانه می‌خواهد.
          </Typography.Text>
          {importFile && (
            <Typography.Text style={{ fontSize: 12 }}>
              فایل انتخاب‌شده: {importFile.name}
            </Typography.Text>
          )}
          {ist === 'importing' && (
            <Space>
              <Spin size="small" />
              <Typography.Text>در حال واردسازی… (فرآیند تراکنشی است)</Typography.Text>
            </Space>
          )}
          {ist === 'error' && (
            <Alert
              type="error"
              showIcon
              message="واردسازی ناموفق بود — همه‌چیز به حالت قبل برگشت"
              description={importStatus.data?.error}
            />
          )}
          {ist === 'done' && importStatus.data?.summary && (
            <Alert
              type="success"
              showIcon
              message="واردسازی کامل شد"
              description={
                `${toFaDigits(Object.keys(importStatus.data.summary.tables).length)} جدول بارگذاری شد` +
                ` — ${toFaDigits(importStatus.data.summary.uploads_moved)} فایل بازگردانده شد.`
              }
            />
          )}
        </Space>
      </Card>
    </div>
  )
}
