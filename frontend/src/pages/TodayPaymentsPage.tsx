import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Col, Row, Space, Statistic, Table, Typography } from 'antd'
import { LeftOutlined, RightOutlined } from '@ant-design/icons'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import type { Page } from '../api/types'
import { formatJalali, formatJalaliTime, formatMoney } from '../lib/jalali'
import FaNumber from '../components/FaNumber'
import { localToday, serverToday } from '../lib/today'
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

interface PaymentTypeStat {
  description: string
  count: number
  total_amount: number
  pos_amount: number
  cash_amount: number
}

function shiftDay(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00`) // midday avoids DST boundary issues
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

export default function TodayPaymentsPage() {
  const [date, setDate] = useState<string>(localToday())
  const [page, setPage] = useState(1)
  useEffect(() => {
    serverToday().then(setDate)
  }, [])
  // a new day starts at page 1
  useEffect(() => {
    setPage(1)
  }, [date])

  const { data, isLoading } = useQuery({
    queryKey: ['payments', date, page],
    queryFn: async () =>
      (await api.get<Page<PatientPayment>>('/payments', {
        params: { date, limit: 50, offset: (page - 1) * 50 },
      })).data,
  })

  const summary = useQuery({
    queryKey: ['payments-summary', date],
    queryFn: async () =>
      (await api.get<PaymentTypeStat[]>('/payments/summary', { params: { date } })).data,
  })

  const items = data?.items ?? []
  // day-wide aggregates come from the unpaged summary endpoint — reducing the
  // current page's items would only ever sum the first 50 rows
  const rows = summary.data ?? []
  const dayTotal = rows.reduce((s, r) => s + r.total_amount, 0)
  const posTotal = rows.reduce((s, r) => s + r.pos_amount, 0)
  const cashTotal = rows.reduce((s, r) => s + r.cash_amount, 0)

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
            <Button
              onClick={async () => setDate(await serverToday())}
            >
              امروز
            </Button>
          </Space>
          <Typography.Text strong style={{ fontSize: 16 }}>
            <FaNumber value={formatJalali(date)} />
          </Typography.Text>
          <Row gutter={[16, 16]}>
            <Col xs={24} sm={12} md={6}>
              <Card>
                <Statistic
                  title="جمع پرداخت‌ها"
                  value={dayTotal}
                  valueRender={() => <FaNumber value={formatMoney(dayTotal)} />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Card>
                <Statistic
                  title="تعداد تراکنش‌ها"
                  value={data?.total ?? 0}
                  valueRender={() => <FaNumber value={data?.total ?? 0} />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Card>
                <Statistic
                  title="کارت‌خوان"
                  value={posTotal}
                  valueRender={() => <FaNumber value={formatMoney(posTotal)} />}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Card>
                <Statistic
                  title="نقدی"
                  value={cashTotal}
                  valueRender={() => <FaNumber value={formatMoney(cashTotal)} />}
                />
              </Card>
            </Col>
          </Row>
          <Table<PaymentTypeStat>
            rowKey="description"
            size="small"
            loading={summary.isLoading}
            dataSource={summary.data ?? []}
            locale={{ emptyText: 'پرداختی در این روز ثبت نشده است' }}
            pagination={false}
            scroll={{ x: 'max-content' }}
            columns={[
              { title: 'نوع پرداخت', dataIndex: 'description' },
              { title: 'تعداد', dataIndex: 'count', render: (n: number) => <FaNumber value={n} /> },
              {
                title: 'جمع کل',
                dataIndex: 'total_amount',
                render: (v: number) => <FaNumber value={formatMoney(v)} />,
              },
              {
                title: 'کارت‌خوان',
                dataIndex: 'pos_amount',
                render: (v: number) => <FaNumber value={formatMoney(v)} />,
              },
              {
                title: 'نقدی',
                dataIndex: 'cash_amount',
                render: (v: number) => <FaNumber value={formatMoney(v)} />,
              },
            ]}
          />
          <Table<PatientPayment>
            rowKey="id"
            size="small"
            loading={isLoading}
            dataSource={items}
            locale={{ emptyText: 'پرداختی در این روز ثبت نشده است' }}
            scroll={{ x: 'max-content' }}
            pagination={{
              current: page,
              pageSize: 50,
              total: data?.total ?? 0,
              onChange: setPage,
              hideOnSinglePage: true,
              showSizeChanger: false,
            }}
            columns={[
              {
                title: 'ساعت',
                dataIndex: 'appointment_scheduled_at',
                render: (v: string) => <FaNumber value={formatJalaliTime(v)} />,
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
              {
                title: 'مبلغ',
                dataIndex: 'amount',
                render: (v: number) => <FaNumber value={formatMoney(v)} />,
              },
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
