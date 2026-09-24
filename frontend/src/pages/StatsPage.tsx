import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Col, Row, Statistic, Table, Typography } from 'antd'

import { api } from '../api/client'
import type { StatsSummary } from '../api/types'
import { formatMoney, toFaDigits } from '../lib/jalali'
import { useUser } from '../components/AppLayout'
import { JalaliRangePicker } from '../components/JalaliDates'

export default function StatsPage() {
  const { hasPerm } = useUser()
  const today = new Date().toISOString().slice(0, 10)
  const [range, setRange] = useState<[string, string]>([today, today])

  const { data, isLoading } = useQuery({
    queryKey: ['stats', range],
    enabled: hasPerm('stats.view'),
    queryFn: async () =>
      (
        await api.get<StatsSummary>('/stats/summary', {
          params: { date_from: range[0], date_to: range[1] },
        })
      ).data,
  })

  if (!hasPerm('stats.view')) {
    return (
      <Card>
        <Typography.Text type="secondary">
          دسترسی به آمار فقط برای پزشک و مدیر مجاز است
        </Typography.Text>
      </Card>
    )
  }

  const downloadCsv = async () => {
    const blob = (await api.get('/stats/summary.csv', {
      params: { date_from: range[0], date_to: range[1] },
      responseType: 'blob',
    })).data
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `stats-${range[0]}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <Typography.Title level={3}>آمار</Typography.Title>
      <Card>
        <Row gutter={[16, 12]}>
          <Col>
            <JalaliRangePicker value={range} onChange={setRange} />
          </Col>
          <Col>
            <Button onClick={downloadCsv}>دریافت CSV</Button>
          </Col>
        </Row>
      </Card>
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={12} md={6}>
          <Card loading={isLoading}>
            <Statistic
              title="تعداد نوبت"
              value={toFaDigits(data?.num_appointments ?? 0)}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card loading={isLoading}>
            <Statistic title="جمع درآمد" value={formatMoney(data?.total_amount ?? 0)} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card loading={isLoading}>
            <Statistic title="کارت‌خوان" value={formatMoney(data?.pos_amount ?? 0)} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card loading={isLoading}>
            <Statistic title="نقدی" value={formatMoney(data?.cash_amount ?? 0)} />
          </Card>
        </Col>
      </Row>
      <Card title="به تفکیک شرح" style={{ marginTop: 16 }} loading={isLoading}>
        <Table
          rowKey="description"
          dataSource={data?.by_description ?? []}
          pagination={false}
          scroll={{ x: 'max-content' }}
          columns={[
            { title: 'شرح', dataIndex: 'description' },
            { title: 'تعداد', dataIndex: 'count', render: toFaDigits },
            { title: 'جمع مبلغ', dataIndex: 'total_amount', render: formatMoney },
          ]}
        />
      </Card>
    </div>
  )
}
