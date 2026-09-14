import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Col, Row, Space, Statistic, Table, Typography } from 'antd'
import { LeftOutlined, RightOutlined } from '@ant-design/icons'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import type { Page } from '../api/types'
import { formatJalali, formatJalaliTime, formatMoney, toFaDigits } from '../lib/jalali'
import { JalaliDatePicker } from '../components/JalaliDates'

export interface PatientPayment {
  id: number
  appointment_id: number
  appointment_scheduled_at: string
  patient_id: number
  patient_first_name: string
  patient_last_name: string
  description: string
  amount: number
  pos: boolean
}

function shiftDay(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00`) // midday avoids DST boundary issues
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

export default function TodayPaymentsPage() {
  const [date, setDate] = useState<string>(new Date().toISOString().slice(0, 10))

  const { data, isLoading } = useQuery({
    queryKey: ['payments', date],
    queryFn: async () =>
      (await api.get<Page<PatientPayment>>('/payments', { params: { date } })).data,
  })

  const items = data?.items ?? []
  const total = items.reduce((s, p) => s + p.amount, 0)

  return (
    <div>
      <Typography.Title level={3}>پرداخت‌های امروز</Typography.Title>
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
            <Button onClick={() => setDate(new Date().toISOString().slice(0, 10))}>
              امروز
            </Button>
          </Space>
          <Typography.Text strong style={{ fontSize: 16 }}>
            {formatJalali(date)}
          </Typography.Text>
          <Row gutter={16}>
            <Col span={8}>
              <Card>
                <Statistic title="جمع پرداخت‌ها" value={formatMoney(total)} />
              </Card>
            </Col>
            <Col span={8}>
              <Card>
                <Statistic title="تعداد تراکنش‌ها" value={toFaDigits(data?.total ?? 0)} />
              </Card>
            </Col>
          </Row>
          <Table<PatientPayment>
            rowKey="id"
            size="small"
            loading={isLoading}
            dataSource={items}
            locale={{ emptyText: 'پرداختی در این روز ثبت نشده است' }}
            pagination={
              (data?.total ?? 0) > 50 ? { pageSize: 50, total: data?.total } : false
            }
            columns={[
              {
                title: 'ساعت',
                dataIndex: 'appointment_scheduled_at',
                render: (v: string) => formatJalaliTime(v),
                width: 90,
              },
              {
                title: 'بیمار',
                render: (_, p) => (
                  <Link to={`/patients/${p.patient_id}?appt=${p.appointment_id}`}>
                    {`${p.patient_first_name} ${p.patient_last_name}`}
                  </Link>
                ),
              },
              { title: 'شرح', dataIndex: 'description' },
              { title: 'مبلغ', dataIndex: 'amount', render: formatMoney },
              {
                title: 'روش پرداخت',
                dataIndex: 'pos',
                render: (pos: boolean) => (pos ? 'کارت‌خوان' : 'نقدی'),
              },
            ]}
          />
        </Space>
      </Card>
    </div>
  )
}
