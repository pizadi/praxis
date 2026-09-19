import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Card,
  Empty,
  Select,
  Space,
  Table,
  Tooltip,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DownloadOutlined } from '@ant-design/icons'

import { api } from '../api/client'
import type { Page, QuestionnaireResponseReport, QuestionnaireTemplate } from '../api/types'
import type { FormatDoc, MergedCell } from '../lib/questionnaire'
import { mergeResponse } from '../lib/questionnaire'
import { formatJalali, toFaDigits } from '../lib/jalali'
import { useUser } from '../components/AppLayout'

const PAGE_SIZE = 20
const CSV_MAX_ROWS = 5000

/** Plain-text rendering of one answer cell (used by the table and the CSV). */
function cellText(merged: MergedCell): string {
  const { question: q, value, status } = merged
  if (status === 'missing') return ''
  if (status === 'invalid') return String(value ?? '')
  if (q.type === 'choice') return q.options.find((o) => o.value === value)?.label ?? String(value)
  if (q.type === 'number') return String(value) + (q.unit ? ` ${q.unit}` : '')
  return String(value ?? '')
}

function csvEscape(v: string): string {
  return /[",\r\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v
}

export default function QuestionnaireResponsesPage() {
  const { hasPerm } = useUser()
  const canRead = hasPerm('questionnaires.read')

  const [templateId, setTemplateId] = useState<number | null>(null)
  const [offset, setOffset] = useState(0)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  const templates = useQuery({
    queryKey: ['questionnaire-templates'],
    queryFn: async () =>
      (await api.get<Page<QuestionnaireTemplate>>('/questionnaires/templates', {
        params: { limit: 200 },
      })).data,
    enabled: canRead,
  })

  const report = useQuery({
    queryKey: ['questionnaire-responses-report', templateId, offset],
    queryFn: async () =>
      (await api.get<Page<QuestionnaireResponseReport>>('/questionnaires/responses', {
        params: { template_id: templateId, limit: PAGE_SIZE, offset },
      })).data,
    enabled: canRead && templateId != null,
  })

  const template = (templates.data?.items ?? []).find((t) => t.id === templateId) ?? null
  const format = (template?.format as FormatDoc | undefined) ?? undefined
  const questions = useMemo(() => format?.questions ?? [], [format])

  const hasScoring = useMemo(
    () =>
      !!format &&
      (!!format.score_formula?.trim() ||
        questions.some(
          (q) =>
            q.type === 'choice' && q.options.some((o) => typeof o.score === 'number'),
        )),
    [format, questions],
  )

  const columns: ColumnsType<QuestionnaireResponseReport> = useMemo(() => {
    const cols: ColumnsType<QuestionnaireResponseReport> = [
      {
        title: 'کد ملی',
        key: 'national_id',
        width: 130,
        render: (_, r) => (
          <span dir="ltr" style={{ fontFamily: 'monospace' }}>
            {toFaDigits(r.patient_national_id)}
          </span>
        ),
      },
      {
        title: 'تاریخ',
        key: 'date',
        width: 110,
        render: (_, r) => formatJalali(r.created_at),
      },
    ]
    for (const q of questions) {
      cols.push({
        title: (
          <Tooltip title={`کلید: ${q.key}`}>{q.label}</Tooltip>
        ),
        key: q.key,
        render: (_, r) => {
          if (!format) return null
          const merged = mergeResponse(format, r.answers)
          const cell = merged.rows.find((row) => row.question.key === q.key)
          if (!cell || cell.status === 'missing') {
            return <Typography.Text type="secondary">—</Typography.Text>
          }
          if (cell.status === 'invalid') {
            return (
              <Tooltip title={`${cell.reason} — مقدار ذخیره‌شده: ${String(cell.value)}`}>
                <Typography.Text type="warning">{String(cell.value)}</Typography.Text>
              </Tooltip>
            )
          }
          const text = cellText(cell)
          if (cell.question.type === 'string' && text.length > 40) {
            return <Tooltip title={text}>{text.slice(0, 40)}…</Tooltip>
          }
          return <span style={{ whiteSpace: 'pre-wrap' }}>{text}</span>
        },
      })
    }
    if (hasScoring) {
      cols.push({
        title: 'جمع نمره',
        key: 'score',
        width: 100,
        render: (_, r) => {
          if (!format) return null
          const merged = mergeResponse(format, r.answers)
          return merged.totalScore !== null ? (
            <Typography.Text strong>{merged.totalScore}</Typography.Text>
          ) : (
            <Typography.Text type="secondary">—</Typography.Text>
          )
        },
      })
    }
    return cols
  }, [questions, format, hasScoring])

  /** Fetch every page for the selected template (capped) and download CSV. */
  const exportCsv = async () => {
    if (templateId == null || !format) return
    setExporting(true)
    setExportError(null)
    try {
      const all: QuestionnaireResponseReport[] = []
      let off = 0
      for (;;) {
        const page = (
          await api.get<Page<QuestionnaireResponseReport>>('/questionnaires/responses', {
            params: { template_id: templateId, limit: 100, offset: off },
          })
        ).data
        all.push(...page.items)
        off += 100
        if (page.items.length === 0 || all.length >= page.total || all.length >= CSV_MAX_ROWS) {
          break
        }
      }
      const header = ['کد ملی', 'تاریخ', ...questions.map((q) => q.label)]
      if (hasScoring) header.push('جمع نمره')
      const lines = [header.map(csvEscape).join(',')]
      for (const r of all) {
        const merged = mergeResponse(format, r.answers)
        const byKey = new Map(merged.rows.map((row) => [row.question.key, row]))
        const row = [
          r.patient_national_id,
          formatJalali(r.created_at),
          ...questions.map((q) => {
            const cell = byKey.get(q.key)
            return cell ? cellText(cell) : ''
          }),
        ]
        if (hasScoring) row.push(merged.totalScore !== null ? String(merged.totalScore) : '')
        lines.push(row.map(csvEscape).join(','))
      }
      const blob = new Blob(['\uFEFF' + lines.join('\r\n')], {
        type: 'text/csv;charset=utf-8',
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `questionnaire-responses-${templateId}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setExportError('دریافت اطلاعات برای خروجی CSV ناموفق بود')
    } finally {
      setExporting(false)
    }
  }

  if (!canRead) {
    return (
      <div>
        <Typography.Title level={3}>گزارش پاسخ‌های پرسش‌نامه‌ها</Typography.Title>
        <Empty description="دسترسی مشاهده پرسش‌نامه‌ها را ندارید" style={{ marginTop: 80 }} />
      </div>
    )
  }

  const total = report.data?.total ?? 0

  return (
    <div>
      <Typography.Title level={3}>گزارش پاسخ‌های پرسش‌نامه‌ها</Typography.Title>
      <Card>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Space wrap>
            <Select<number>
              showSearch
              optionFilterProp="label"
              placeholder="انتخاب پرسش‌نامه"
              style={{ width: 320 }}
              value={templateId ?? undefined}
              onChange={(v) => {
                setTemplateId(v)
                setOffset(0)
              }}
              options={(templates.data?.items ?? []).map((t) => ({
                value: t.id,
                label: t.name,
              }))}
            />
            <Button
              icon={<DownloadOutlined />}
              disabled={templateId == null || total === 0}
              loading={exporting}
              onClick={exportCsv}
            >
              خروجی CSV
            </Button>
          </Space>

          {exportError && <Alert type="error" showIcon message={exportError} />}

          <Table<QuestionnaireResponseReport>
            rowKey="id"
            loading={report.isFetching}
            dataSource={report.data?.items ?? []}
            columns={columns}
            scroll={{ x: 'max-content' }}
            locale={{ emptyText: <Empty description="پاسخی یافت نشد" /> }}
            pagination={{
              total,
              pageSize: PAGE_SIZE,
              current: Math.floor(offset / PAGE_SIZE) + 1,
              showSizeChanger: false,
              showTotal: (t, range) =>
                `${toFaDigits(range[0])}–${toFaDigits(range[1])} از ${toFaDigits(t)}`,
              onChange: (_page, pageSize) => setOffset((pageSize - 1) * PAGE_SIZE),
            }}
          />
        </Space>
      </Card>
    </div>
  )
}
