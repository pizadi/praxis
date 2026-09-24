import { Button, Card, Empty, List, Popconfirm, Space, Typography } from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { theme as antdTheme } from 'antd'

import type { QuestionnaireResponse } from '../../api/types'
import { formatJalali } from '../../lib/jalali'

interface Props {
  responses: QuestionnaireResponse[]
  loading: boolean
  selectedId: number | null
  canFill: boolean
  templatesTotal: number
  onSelect: (responseId: number) => void
  onDelete: (responseId: number) => void
  onNew: () => void
}

/** Sidebar list of a patient's questionnaire responses. */
export default function QuestionnaireSidebarCard({
  responses,
  loading,
  selectedId,
  canFill,
  templatesTotal,
  onSelect,
  onDelete,
  onNew,
}: Props) {
  const { token } = antdTheme.useToken()
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
        renderItem={(response) => (
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
                  {formatJalali(response.created_at)}
                  {response.created_by_username
                    ? ` — ${response.created_by_username}`
                    : ''}
                </Typography.Text>
              </Space>
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
          </List.Item>
        )}
      />
    </Card>
  )
}
