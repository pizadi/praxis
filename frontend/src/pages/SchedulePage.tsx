import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App as AntApp, Button, Card, List, Space, Tag, Tooltip, Typography } from 'antd'
import { DoubleLeftOutlined, LeftOutlined, RightOutlined } from '@ant-design/icons'
import { Link } from 'react-router-dom'

import { api, apiError } from '../api/client'
import type { AppointmentBrief, Page } from '../api/types'
import { formatJalali, formatJalaliTime, toFaDigits } from '../lib/jalali'
import { LAST_STAGE, stageOf } from '../lib/stages'
import { localToday, serverToday } from '../lib/today'
import { JalaliDatePicker } from '../components/JalaliDates'
import { useUser } from '../components/AppLayout'

function shiftDay(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00`) // midday avoids DST boundary issues
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

export default function SchedulePage() {
  const [date, setDate] = useState<string>(localToday())
  const { hasPerm } = useUser()
  const { message } = AntApp.useApp()
  const qc = useQueryClient()
  useEffect(() => {
    serverToday().then(setDate)
  }, [])

  const { data, isLoading } = useQuery({
    queryKey: ['schedule', date],
    queryFn: async () =>
      (await api.get<Page<AppointmentBrief>>('/appointments', {
        params: { date_from: date, date_to: date, limit: 100 },
      })).data,
  })

  // quick check-in: one click to the next stage (regression lives on the
  // appointment panel, behind a confirmation)
  const advance = useMutation({
    mutationFn: async (id: number) =>
      api.patch(`/appointments/${id}/stage`, { direction: 'advance' }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['schedule'] })
      await qc.invalidateQueries({ queryKey: ['patient-appointments'] })
      await qc.invalidateQueries({ queryKey: ['appointment'] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  return (
    <div>
      <Typography.Title level={3}>برنامه روزانه</Typography.Title>
      <Card>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Space wrap>
            <Button icon={<RightOutlined />} onClick={() => setDate(shiftDay(date, -1))}>
              روز قبل
            </Button>
            <JalaliDatePicker value={date} onChange={(d) => d && setDate(d)} />
            <Button icon={<LeftOutlined />} onClick={() => setDate(shiftDay(date, 1))}>
              روز بعد
            </Button>
            <Button
              onClick={async () => setDate(await serverToday())}
            >
              امروز
            </Button>
          </Space>
          <Typography.Text strong style={{ fontSize: 16 }}>
            {formatJalali(date)}
          </Typography.Text>
          <List
            loading={isLoading}
            dataSource={data?.items ?? []}
            locale={{ emptyText: 'نوبتی در این روز نیست' }}
            renderItem={(a) => {
              const stage = stageOf(a.stage)
              return (
                <List.Item
                  actions={[
                    <Link key="d" to={`/patients/${a.patient_id}?appt=${a.id}`}>
                      جزئیات
                    </Link>,
                    ...(hasPerm('appointments.stage') && a.stage < LAST_STAGE
                      ? [
                          <Tooltip key="s" title={`به مرحله «${stageOf(a.stage + 1).label}»`}>
                            <Button
                              size="small"
                              icon={<DoubleLeftOutlined />}
                              loading={advance.isPending && advance.variables === a.id}
                              onClick={() => advance.mutate(a.id)}
                            >
                              {stageOf(a.stage + 1).label}
                            </Button>
                          </Tooltip>,
                        ]
                      : []),
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <Space size={8} wrap>
                        <span>
                          {formatJalaliTime(a.scheduled_at)} — {a.patient_first_name}{' '}
                          {a.patient_last_name}
                        </span>
                        <Tag color={stage.color}>{stage.label}</Tag>
                      </Space>
                    }
                    description={`کد ملی: ${toFaDigits(a.patient_national_id)}`}
                  />
                </List.Item>
              )
            }}
          />
        </Space>
      </Card>
    </div>
  )
}
