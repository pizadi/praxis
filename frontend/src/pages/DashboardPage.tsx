import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, Col, List, Row, Statistic, Typography } from 'antd'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import type { AppointmentBrief, Page } from '../api/types'
import { formatJalaliTime, toFaDigits } from '../lib/jalali'
import { localToday, serverToday } from '../lib/today'

export default function DashboardPage() {
  const [today, setToday] = useState(localToday())
  useEffect(() => {
    serverToday().then(setToday)
  }, [])

  const { data, isLoading } = useQuery({
    queryKey: ['appointments', { date_from: today, date_to: today }],
    queryFn: async () =>
      (await api.get<Page<AppointmentBrief>>('/appointments', {
        params: { date_from: today, date_to: today, limit: 100 },
      })).data,
  })

  const items = data?.items ?? []

  return (
    <div>
      <Typography.Title level={3}>داشبورد — نوبت‌های امروز</Typography.Title>
      <Row gutter={16}>
        <Col span={8}>
          <Card>
            <Statistic title="نوبت‌های امروز" value={toFaDigits(data?.total ?? 0)} />
          </Card>
        </Col>
      </Row>
      <Card title="فهرست نوبت‌ها" style={{ marginTop: 16 }} loading={isLoading}>
        <List
          dataSource={items}
          locale={{ emptyText: 'نوبتی برای امروز ثبت نشده است' }}
          renderItem={(a) => (
            <List.Item
              actions={[
                <Link key="appt" to={`/patients/${a.patient_id}?appt=${a.id}`}>
                  جزئیات
                </Link>,
              ]}
            >
              <List.Item.Meta
                title={`${a.patient_first_name} ${a.patient_last_name}`}
                description={`ساعت ${formatJalaliTime(a.scheduled_at)} — کد ملی ${toFaDigits(
                  a.patient_national_id,
                )}`}
              />
            </List.Item>
          )}
        />
      </Card>
    </div>
  )
}
