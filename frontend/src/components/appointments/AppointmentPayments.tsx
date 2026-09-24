import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App as AntApp,
  AutoComplete,
  Button,
  Card,
  Col,
  Form,
  Popconfirm,
  Radio,
  Row,
  Space,
  Statistic,
  Table,
} from 'antd'

import { api, apiError } from '../../api/client'
import type { Transaction } from '../../api/types'
import DigitInput from '../DigitInput'
import { formatMoney } from '../../lib/jalali'

interface Props {
  appointmentId: number
}

/** Payment history and quick-add form for one appointment. */
export default function AppointmentPayments({ appointmentId }: Props) {
  const { message } = AntApp.useApp()
  const queryClient = useQueryClient()
  const [form] = Form.useForm<{ description: string; amount: number; pos: boolean }>()

  const transactions = useQuery({
    queryKey: ['appointment-txns', appointmentId],
    queryFn: async () =>
      (await api.get<{ items: Transaction[] }>(
        `/appointments/${appointmentId}/transactions`,
        { params: { limit: 100 } },
      )).data,
  })

  const addTransaction = useMutation({
    mutationFn: async (values: {
      description: string
      amount: number
      pos: boolean
    }) => api.post(`/appointments/${appointmentId}/transactions`, values),
    onSuccess: () => {
      message.success('تراکنش ثبت شد')
      form.resetFields()
      queryClient.invalidateQueries({ queryKey: ['appointment-txns', appointmentId] })
    },
    onError: (error) => message.error(apiError(error).message),
  })

  const deleteTransaction = useMutation({
    mutationFn: async (transactionId: number) =>
      api.delete(`/appointments/transactions/${transactionId}`),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['appointment-txns', appointmentId] }),
    onError: (error) => message.error(apiError(error).message),
  })

  const items = transactions.data?.items ?? []

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} md={8}>
          <Card>
            <Statistic
              title="جمع کل"
              value={formatMoney(items.reduce((sum, transaction) => sum + transaction.amount, 0))}
            />
          </Card>
        </Col>
      </Row>

      <Form
        form={form}
        layout="inline"
        initialValues={{ pos: true }}
        onFinish={(values) =>
          addTransaction.mutate({
            description: values.description,
            amount: Number(values.amount),
            pos: values.pos,
          })
        }
      >
        <Form.Item name="description" rules={[{ required: true }]}>
          <AutoComplete
            options={[{ value: 'ویزیت' }, { value: 'اسپیرو' }]}
            placeholder="شرح (مثلاً ویزیت)"
            style={{ width: 180 }}
          />
        </Form.Item>
        <Form.Item
          name="amount"
          rules={[
            { required: true },
            { pattern: /^\d+$/, message: 'مبلغ فقط عدد است' },
          ]}
        >
          <DigitInput inputMode="numeric" placeholder="مبلغ" />
        </Form.Item>
        <Form.Item name="pos" label="روش">
          <Radio.Group>
            <Radio.Button value={true}>کارت‌خوان</Radio.Button>
            <Radio.Button value={false}>نقدی</Radio.Button>
          </Radio.Group>
        </Form.Item>
        <Button htmlType="submit" loading={addTransaction.isPending}>
          افزودن
        </Button>
      </Form>

      <Table<Transaction>
        rowKey="id"
        dataSource={items}
        loading={transactions.isLoading}
        pagination={false}
        size="small"
        scroll={{ x: 'max-content' }}
        columns={[
          { title: 'شرح', dataIndex: 'description' },
          { title: 'مبلغ', dataIndex: 'amount', render: formatMoney },
          {
            title: 'نوع',
            dataIndex: 'pos',
            render: (pos: boolean) => (pos ? 'کارت‌خوان' : 'نقدی'),
          },
          {
            title: '',
            render: (_, transaction) => (
              <Popconfirm
                title="تراکنش به سبد بازیافت منتقل شود؟"
                onConfirm={() => deleteTransaction.mutate(transaction.id)}
              >
                <Button size="small" danger>
                  حذف
                </Button>
              </Popconfirm>
            ),
          },
        ]}
      />
    </Space>
  )
}
