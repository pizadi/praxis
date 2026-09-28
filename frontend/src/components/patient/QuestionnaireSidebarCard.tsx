import { Button, Card, Empty, List, Popconfirm, Space, Tag, Typography } from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { theme as antdTheme } from 'antd'

import type { QuestionnaireResponse, QuestionnaireTemplate } from '../../api/types'
import { formatJalali } from '../../lib/jalali'
import { mergeResponse } from '../../lib/questionnaire'
import FaNumber from '../FaNumber'

interface Props {
  responses: QuestionnaireResponse[]
  loading: boolean
  selectedId: number | null
  canFill: boolean
  templatesTotal: number
  /** live templates — the score is computed against the CURRENT format */
  templates: QuestionnaireTemplate[]
  onSelect: (responseId: number) => void
  onDelete: (responseId: number) => void
  onNew: () => void
}

/** Sidebar list of a patient's questionnaire responses. Scored templates show
 * the response total ('—' when it cannot be computed — a score is never
 * invented); unscored templates show nothing. */
export default function QuestionnaireSidebarCard({
  responses,
  loading,
  selectedId,
  canFill,
  templatesTotal,
  templates,
  onSelect,
  onDelete,
  onNew,
}: Props) {
  const { token } = antdTheme.useToken()

  /** null = the template is unscored (or gone — show nothing); otherwise the
   * response total, null when not computable. */
  const scoreOf = (response: QuestionnaireResponse): { total: number | null } | null => {
    const template = templates.find((t) => t.id === response.template_id)
    if (!template) return null
    const { scored, totalScore } = mergeResponse(template.format, response.answers)
    return scored ? { total: totalScore } : null
  }

  return (
    <Card
      title="پرسش‌نامه‌ها"
      extra={
        canFill && (
          <Button
            type="primary"
            size="small"
            icon={<PlusOutlined />}
            disabled={templatesTotal === 0}
            title={templatesTotal === 0 ? 'هیچ قالبی تعریف نشده است' : undefined}
            onClick={onNew}
          >
            پرسش‌نامه جدید
          </Button>
        )
      }
      styles={{ body: { padding: 0, maxHeight: '48vh', overflowY: 'auto' } }}
    >
      <List
        loading={loading}
        dataSource={responses}
        locale={{ emptyText: <Empty description="پاسخی ثبت نشده است" /> }}
        renderItem={(response) => {
          const score = scoreOf(response)
          return (
            <List.Item
              style={{
                cursor: 'pointer',
                paddingInline: 16,
                background: selectedId === response.id ? token.colorPrimaryBg : undefined,
              }}
              onClick={() => onSelect(response.id)}
            >
              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                <Space direction="vertical" size={0}>
                  <Typography.Text strong>{response.template_name}</Typography.Text>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    <FaNumber value={formatJalali(response.created_at)} />
                    {response.created_by_username
                      ? ` — ${response.created_by_username}`
                      : ''}
                  </Typography.Text>
                </Space>
                <Space size={4}>
                  {score && (
                    <Tag
                      style={{ marginInlineEnd: 0 }}
                      onClick={(event) => event.stopPropagation()}
                    >
                      امتیاز: {score.total === null ? '—' : <FaNumber value={score.total} />}
                    </Tag>
                  )}
                  {canFill && (
                    <Popconfirm
                      title="پاسخ به سبد بازیافت منتقل شود؟"
                      onConfirm={(event) => {
                        event?.stopPropagation()
                        onDelete(response.id)
                      }}
                      onCancel={(event) => event?.stopPropagation()}
                    >
                      <Button
                        size="small"
                        type="text"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={(event) => event.stopPropagation()}
                      />
                    </Popconfirm>
                  )}
                </Space>
              </Space>
            </List.Item>
          )
        }}
      />
    </Card>
  )
}
