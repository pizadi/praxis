import { Button, Space, Tag, Tooltip } from 'antd'
import { DoubleLeftOutlined, DoubleRightOutlined } from '@ant-design/icons'

import { LAST_STAGE, stageOf } from '../../lib/stages'

interface Props {
  stage: number
  canChange: boolean
  onAdvance: () => void
  onRegress: () => void
}

/** Visit-stage tag with bounded ±1 controls. */
export default function AppointmentStageHeader({
  stage,
  canChange,
  onAdvance,
  onRegress,
}: Props) {
  const current = stageOf(stage)
  if (!canChange) {
    return <Tag color={current.color}>{current.label}</Tag>
  }
  return (
    <Space size={8}>
      <Tag color={current.color} style={{ marginInlineEnd: 0 }}>
        {current.label}
      </Tag>
      <Space size={4}>
        <Tooltip title="مرحله قبل">
          <Button
            size="small"
            icon={<DoubleRightOutlined />}
            disabled={stage === 0}
            onClick={onRegress}
          />
        </Tooltip>
        <Tooltip title="مرحله بعد">
          <Button
            size="small"
            icon={<DoubleLeftOutlined />}
            disabled={stage === LAST_STAGE}
            onClick={onAdvance}
          />
        </Tooltip>
      </Space>
    </Space>
  )
}
