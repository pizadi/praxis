import { useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  App as AntApp,
  Button,
  Card,
  Descriptions,
  Empty,
  Space,
  Spin,
  Tooltip,
  Typography,
  Upload,
  theme,
} from 'antd'
import {
  DownloadOutlined,
  FileAddOutlined,
  SwapOutlined,
  UndoOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
} from '@ant-design/icons'
import type { RcFile } from 'antd/es/upload'

import type { Attachment } from '../api/types'
import { api, apiError } from '../api/client'
import { downloadAttachment } from '../lib/files'
import { fileSize, formatJalali, toFaDigits } from '../lib/jalali'
import { useUser } from './AppLayout'
import FileNotesExpanded from './FileNotesExpanded'

const EXT_MIME: Record<string, string> = {
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  gif: 'image/gif',
  webp: 'image/webp',
  bmp: 'image/bmp',
  svg: 'image/svg+xml',
  pdf: 'application/pdf',
}

const MIN_SCALE = 0.25
const MAX_SCALE = 4
const ZOOM_STEP = 1.25

/** image / pdf → previewable kind (mime_type first, extension fallback) */
function previewKind(file: Attachment): 'image' | 'pdf' | null {
  if (file.missing_file || !file.original_filename) return null
  const mime = file.mime_type?.toLowerCase() ?? ''
  if (mime.startsWith('image/')) return 'image'
  if (mime === 'application/pdf') return 'pdf'
  const ext = file.original_filename.split('.').pop()?.toLowerCase() ?? ''
  const guessed = EXT_MIME[ext]
  if (guessed?.startsWith('image/')) return 'image'
  if (guessed === 'application/pdf') return 'pdf'
  return null
}

/**
 * Detail pane of one selected file in the patient's «همه فایل‌ها» view:
 * title/notes/upload date + download, and an in-page preview (images with
 * zoom controls, PDFs in the browser viewer) for previewable types.
 */
export default function FileDetailPane({ file }: { file: Attachment }) {
  const { hasPerm } = useUser()
  const { message } = AntApp.useApp()
  const { token: themeToken } = theme.useToken()
  const qc = useQueryClient()
  const kind = useMemo(() => previewKind(file), [file])
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [scale, setScale] = useState(1)
  const [uploading, setUploading] = useState(false)

  /** Attach a physical file to this row (note-only/missing) or replace the
   * current one — via the authorized axios client, never antd auto-upload. */
  const setContent = async (f: RcFile) => {
    const replacing = !!file.original_filename && !file.missing_file
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('file', f)
      await api.post(`/files/${file.id}/content`, fd)
      message.success(replacing ? 'فایل جایگزین شد' : 'فایل پیوست شد')
      await qc.invalidateQueries({ queryKey: ['patient-files'] })
      await qc.invalidateQueries({ queryKey: ['appointment-files'] })
    } catch (err) {
      message.error(apiError(err).message)
    } finally {
      setUploading(false)
    }
  }

  const canWrite = hasPerm('files.write')
  const contentLabel = file.missing_file
    ? 'افزودن مجدد فایل'
    : file.original_filename
      ? 'تغییر فایل'
      : 'افزودن فایل'

  // fetch the bytes (authorized) and build an object URL for the preview;
  // re-runs when the content is (re)placed — stored_filename changes then
  useEffect(() => {
    if (kind == null) return
    let objectUrl: string | null = null
    let cancelled = false
    ;(async () => {
      try {
        const res = await api.get(`/files/${file.id}/download`, {
          responseType: 'blob',
        })
        const objUrl = URL.createObjectURL(res.data)
        if (cancelled) {
          URL.revokeObjectURL(objUrl)
          return
        }
        objectUrl = objUrl
        setUrl(objUrl)
      } catch {
        if (!cancelled) setFailed(true)
      }
    })()
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
      setUrl(null)
      setFailed(false)
    }
  }, [file.id, file.stored_filename, kind])

  useEffect(() => {
    setScale(1)
  }, [file.id])

  const zoom = (dir: 1 | -1) =>
    setScale((s) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, s * dir * ZOOM_STEP)))

  const title = file.original_filename ?? 'فقط یادداشت'

  return (
    <Card
      title={
        <Space>
          <Typography.Text strong>{title}</Typography.Text>
          {file.missing_file && (
            <Typography.Text type="danger">(مفقود)</Typography.Text>
          )}
        </Space>
      }
      extra={
        <Space>
          {canWrite && (
            <Upload
              maxCount={1}
              showUploadList={false}
              disabled={uploading}
              beforeUpload={(f) => {
                void setContent(f)
                return false // block antd auto-upload; we POST via the axios client
              }}
            >
              <Button
                size="small"
                loading={uploading}
                icon={
                  file.original_filename && !file.missing_file ? (
                    <SwapOutlined />
                  ) : (
                    <FileAddOutlined />
                  )
                }
              >
                {contentLabel}
              </Button>
            </Upload>
          )}
          <Button
            type="primary"
            size="small"
            icon={<DownloadOutlined />}
            disabled={file.missing_file || !file.original_filename}
            onClick={async () => {
              try {
                await downloadAttachment(file.id, file.original_filename)
              } catch (err) {
                message.error(apiError(err).message)
              }
            }}
          >
            دانلود
          </Button>
        </Space>
      }
    >
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Descriptions bordered column={1} size="small">
          <Descriptions.Item label="عنوان فایل">
            {file.original_filename ?? (
              <Typography.Text type="secondary">فقط یادداشت (بدون فایل)</Typography.Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="شرح">{file.description || '—'}</Descriptions.Item>
          <Descriptions.Item label="تاریخ بارگذاری">
            {formatJalali(file.created_at, true)}
          </Descriptions.Item>
          <Descriptions.Item label="حجم">{fileSize(file.size_bytes)}</Descriptions.Item>
        </Descriptions>

        <FileNotesExpanded file={file} />

        {kind != null && (
          <>
            {kind === 'image' && (
              <Space wrap align="center">
                <Typography.Text type="secondary">بزرگ‌نمایی:</Typography.Text>
                <Tooltip title="کوچک‌تر">
                  <Button
                    size="small"
                    icon={<ZoomOutOutlined />}
                    disabled={scale <= MIN_SCALE}
                    onClick={() => zoom(-1)}
                  />
                </Tooltip>
                <Typography.Text style={{ minWidth: 48, textAlign: 'center' }}>
                  {toFaDigits(Math.round(scale * 100))}٪
                </Typography.Text>
                <Tooltip title="بزرگ‌تر">
                  <Button
                    size="small"
                    icon={<ZoomInOutlined />}
                    disabled={scale >= MAX_SCALE}
                    onClick={() => zoom(1)}
                  />
                </Tooltip>
                <Tooltip title="اندازه اصلی">
                  <Button
                    size="small"
                    icon={<UndoOutlined />}
                    disabled={scale === 1}
                    onClick={() => setScale(1)}
                  />
                </Tooltip>
              </Space>
            )}
            {url == null && !failed && (
              <div style={{ textAlign: 'center', padding: 40 }}>
                <Spin />
              </div>
            )}
            {failed && (
              <Empty description="پیش‌نمایش در دسترس نیست" style={{ margin: '24px 0' }} />
            )}
            {url != null && kind === 'image' && (
              <div
                style={{
                  overflow: 'auto',
                  maxHeight: '60vh',
                  border: `1px solid ${themeToken.colorBorderSecondary}`,
                  borderRadius: 8,
                  textAlign: 'center',
                }}
              >
                <img
                  src={url}
                  alt={title}
                  style={{
                    width: `${Math.round(scale * 100)}%`,
                    maxWidth: 'none',
                    display: 'block',
                    marginInline: 'auto',
                  }}
                />
              </div>
            )}
            {url != null && kind === 'pdf' && (
              <iframe
                src={url}
                title={title}
                style={{ width: '100%', height: '65vh', border: 0, borderRadius: 8 }}
              />
            )}
          </>
        )}
        {kind == null && !file.missing_file && file.original_filename && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            پیش‌نمایشی برای این نوع فایل موجود نیست — می‌توانید آن را دانلود کنید.
          </Typography.Text>
        )}
      </Space>
    </Card>
  )
}
