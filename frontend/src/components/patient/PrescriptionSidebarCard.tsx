import { Button, Card, Empty, List, Popconfirm, Space, Typography } from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { theme as antdTheme } from 'antd'

import type { Prescription } from '../../api/types'
import { formatJalali } from '../../lib/jalali'

interface Props {
  prescriptions: Prescription[]
  loading: boolean
  selectedId: number | null
  canWrite: boolean
  onSelect: (prescriptionId: number) => void
  onDelete: (prescriptionId: number) => void
  onNew: () => void
}

/** Sidebar history list for a patient's structured prescriptions. */
export default function PrescriptionSidebarCard({
  prescriptions,
  loading,
  selectedId,
  canWrite,
  onSelect,
  onDelete,
  onNew,
}: Props) {
  const { token } = antdTheme.useToken()
  return (
    <Card
      title="نسخه‌ها"
      extra={
        canWrite && (
          <Button type="primary" size="small" icon={<PlusOutlined />} onClick={onNew}>
            نسخه جدید
          </Button>
        )
      }
      styles={{ body: { padding: 0, maxHeight: '48vh', overflowY: 'auto' } }}
    >
      <List
        loading={loading}
        dataSource={prescriptions}
        locale={{ emptyText: <Empty description="نسخه‌ای ثبت نشده است" /> }}
        renderItem={(prescription) => (
          <List.Item
            style={{
              cursor: 'pointer',
              paddingInline: 16,
              background:
                selectedId === prescription.id ? token.colorPrimaryBg : undefined,
            }}
            onClick={() => onSelect(prescription.id)}
          >
            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
              <Space direction="vertical" size={0}>
                <Typography.Text strong>
                  {prescription.items.length > 0
                    ? prescription.items.map((item) => item.item_name).join('، ')
                    : '(بدون قلم)'}
                </Typography.Text>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {formatJalali(prescription.prescribed_at)}
                  {prescription.created_by_username
                    ? ` — ${prescription.created_by_username}`
                    : ''}
                </Typography.Text>
              </Space>
              {canWrite && (
                <Popconfirm
                  title="نسخه به سبد بازیافت منتقل شود؟"
                  onConfirm={(event) => {
                    event?.stopPropagation()
                    onDelete(prescription.id)
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
