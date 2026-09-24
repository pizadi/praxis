import { Button, Card, Empty, List, Popconfirm, Space, Tag, Tooltip, Typography } from 'antd'
import {
  DeleteOutlined,
  DoubleLeftOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import { theme as antdTheme } from 'antd'

import type { AppointmentBrief } from '../../api/types'
import { formatJalali, formatJalaliTime } from '../../lib/jalali'
import { LAST_STAGE, stageOf } from '../../lib/stages'

interface Props {
  appointments: AppointmentBrief[]
  loading: boolean
  selectedId: number | null
  canStage: boolean
  canDelete: boolean
  advancingId?: number
  onSelect: (appointmentId: number) => void
  onAdvance: (appointmentId: number) => void
  onDelete: (appointmentId: number) => void
  onNew: () => void
}

/** Sidebar list of a patient's appointments with quick stage advance. */
export default function AppointmentSidebarCard({
  appointments,
  loading,
  selectedId,
  canStage,
  canDelete,
  advancingId,
  onSelect,
  onAdvance,
  onDelete,
  onNew,
}: Props) {
  const { token } = antdTheme.useToken()
  return (
    <Card
      title="نوبت‌ها"
      extra={
        <Button type="primary" size="small" icon={<PlusOutlined />} onClick={onNew}>
          نوبت جدید
        </Button>
      }
      styles={{ body: { padding: 0, maxHeight: '48vh', overflowY: 'auto' } }}
    >
      <List
        loading={loading}
        dataSource={appointments}
        locale={{ emptyText: <Empty description="نوبتی ثبت نشده است" /> }}
        renderItem={(appointment) => {
          const stage = stageOf(appointment.stage)
          return (
            <List.Item
              style={{
                cursor: 'pointer',
                paddingInline: 16,
                background: selectedId === appointment.id ? token.colorPrimaryBg : undefined,
              }}
              onClick={() => onSelect(appointment.id)}
            >
              <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                <Space direction="vertical" size={0}>
                  <Space size={6} wrap>
                    <Typography.Text strong>
                      {formatJalali(appointment.scheduled_at)}
                    </Typography.Text>
                    <Tag
                      color={stage.color}
                      style={{ marginInlineEnd: 0, fontSize: 11, lineHeight: '16px' }}
                    >
                      {stage.label}
                    </Tag>
                  </Space>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    ساعت {formatJalaliTime(appointment.scheduled_at)}
                  </Typography.Text>
                </Space>
                <Space>
                  {canStage && appointment.stage < LAST_STAGE && (
                    <Tooltip title={`به مرحله «${stageOf(appointment.stage + 1).label}»`}>
                      <Button
                        size="small"
                        type="text"
                        icon={<DoubleLeftOutlined />}
                        loading={advancingId === appointment.id}
                        onClick={(event) => {
                          event.stopPropagation()
                          onAdvance(appointment.id)
                        }}
                      />
                    </Tooltip>
                  )}
                  {canDelete && (
                    <Popconfirm
                      title="نوبت به سبد بازیافت منتقل شود؟"
                      onConfirm={(event) => {
                        event?.stopPropagation()
                        onDelete(appointment.id)
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
