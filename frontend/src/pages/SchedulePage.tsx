import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, List, Space, Typography } from 'antd'
import { LeftOutlined, RightOutlined } from '@ant-design/icons'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import type { AppointmentBrief, Page } from '../api/types'
import { formatJalali, formatJalaliTime, toFaDigits } from '../lib/jalali'
import { localToday, serverToday } from '../lib/today'
import { JalaliDatePicker } from '../components/JalaliDates'

function shiftDay(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00`) // midday avoids DST boundary issues
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

export default function SchedulePage() {
  const [date, setDate] = useState<string>(localToday())
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
            renderItem={(a) => (
              <List.Item
                actions={[
                  <Link key="d" to={`/patients/${a.patient_id}?appt=${a.id}`}>
                    جزئیات
                  </Link>,
                ]}
              >
                <List.Item.Meta
                  title={`${formatJalaliTime(a.scheduled_at)} — ${a.patient_first_name} ${a.patient_last_name}`}
                  description={`کد ملی: ${toFaDigits(a.patient_national_id)}`}
                />
              </List.Item>
            )}
          />
        </Space>
      </Card>
    </div>
  )
}
