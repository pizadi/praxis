import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  App as AntApp,
  Button,
  Card,
  Col,
  Input,
  Popconfirm,
  Row,
  Select,
  Space,
  Table,
  Tag,
} from 'antd'
import { ClearOutlined } from '@ant-design/icons'
import { Link } from 'react-router-dom'

import { api, apiError } from '../api/client'
import type { NamedRef, Page, Patient } from '../api/types'
import { toEnDigits, toFaDigits } from '../lib/jalali'
import { useUser } from '../components/AppLayout'
import PatientFormModal from '../components/PatientFormModal'

interface PatientFilters {
  first_name: string
  last_name: string
  national_id: string
  phone: string
  insurance: string
  year_of_birth: string
  gender: number | null
  tag_ids: number[]
  diagnosis_ids: number[]
}

const EMPTY_FILTERS: PatientFilters = {
  first_name: '',
  last_name: '',
  national_id: '',
  phone: '',
  insurance: '',
  year_of_birth: '',
  gender: null,
  tag_ids: [],
  diagnosis_ids: [],
}

export default function PatientsPage() {
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  // advanced filters (all applied SQL-side; digits normalized to ASCII)
  const [filters, setFilters] = useState<PatientFilters>(EMPTY_FILTERS)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const { hasPerm } = useUser()
  const { message } = AntApp.useApp()
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<Patient | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['patients', q, page, filters],
    queryFn: async () =>
      (await api.get<Page<Patient>>('/patients', {
        params: {
          q: q || undefined,
          first_name: filters.first_name || undefined,
          last_name: filters.last_name || undefined,
          national_id: toEnDigits(filters.national_id) || undefined,
          phone: toEnDigits(filters.phone) || undefined,
          insurance: filters.insurance || undefined,
          year_of_birth: toEnDigits(filters.year_of_birth) || undefined,
          gender: filters.gender ?? undefined,
          tag_ids: filters.tag_ids.length ? filters.tag_ids.join(',') : undefined,
          diagnosis_ids: filters.diagnosis_ids.length
            ? filters.diagnosis_ids.join(',')
            : undefined,
          limit: 20,
          offset: (page - 1) * 20,
        },
      })).data,
  })

  const tags = useQuery({
    queryKey: ['tags'],
    queryFn: async () => (await api.get<NamedRef[]>('/tags')).data,
  })
  const diagnoses = useQuery({
    queryKey: ['diagnoses'],
    queryFn: async () => (await api.get<NamedRef[]>('/diagnoses')).data,
  })

  const remove = useMutation({
    mutationFn: async (id: number) => api.delete(`/patients/${id}`),
    onSuccess: () => {
      message.success('بیمار به سبد بازیافت منتقل شد')
      setAdvancedOpen(false)
    },
    onError: (err) => message.error(apiError(err).message),
  })

  return (
    <div>
      <Card
        title="بیماران"
        extra={
          <Button
            type="primary"
            onClick={() => {
              setEditing(null)
              setModalOpen(true)
            }}
          >
            بیمار جدید
          </Button>
        }
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Input.Search
            placeholder="جستجو بر اساس نام، کد ملی یا شماره تلفن…"
            allowClear
            onSearch={(v) => {
              setQ(v)
              setPage(1)
            }}
          />
          <Button
            size="small"
            type={advancedOpen ? 'primary' : 'link'}
            onClick={() => setAdvancedOpen((o) => !o)}
          >
            {advancedOpen ? 'بستن فیلترها' : 'فیلترهای بیشتر'}
          </Button>
          {advancedOpen && (
            <Row gutter={[12, 12]}>
                <Col xs={12} md={6}>
                  <Input
                    placeholder="نام"
                    allowClear
                    value={filters.first_name}
                    onChange={(e) => {
                      setFilters((f) => ({ ...f, first_name: e.target.value }))
                      setPage(1)
                    }}
                  />
                </Col>
                <Col xs={12} md={6}>
                  <Input
                    placeholder="نام خانوادگی"
                    allowClear
                    value={filters.last_name}
                    onChange={(e) => {
                      setFilters((f) => ({ ...f, last_name: e.target.value }))
                      setPage(1)
                    }}
                  />
                </Col>
                <Col xs={12} md={6}>
                  <Input
                    placeholder="کد ملی"
                    allowClear
                    value={filters.national_id}
                    onChange={(e) => {
                      setFilters((f) => ({ ...f, national_id: e.target.value }))
                      setPage(1)
                    }}
                  />
                </Col>
                <Col xs={12} md={6}>
                  <Input
                    placeholder="شماره تلفن"
                    allowClear
                    value={filters.phone}
                    onChange={(e) => {
                      setFilters((f) => ({ ...f, phone: e.target.value }))
                      setPage(1)
                    }}
                  />
                </Col>
                <Col xs={12} md={6}>
                  <Input
                    placeholder="بیمه"
                    allowClear
                    value={filters.insurance}
                    onChange={(e) => {
                      setFilters((f) => ({ ...f, insurance: e.target.value }))
                      setPage(1)
                    }}
                  />
                </Col>
                <Col xs={12} md={6}>
                  <Input
                    placeholder="سال تولد"
                    allowClear
                    style={{ width: '100%' }}
                    value={filters.year_of_birth}
                    onChange={(e) => {
                      setFilters((f) => ({ ...f, year_of_birth: e.target.value }))
                      setPage(1)
                    }}
                  />
                </Col>
                <Col xs={12} md={6}>
                  <Select
                    placeholder="جنسیت"
                    style={{ width: '100%' }}
                    allowClear
                    options={[
                      { value: 0, label: 'مرد' },
                      { value: 1, label: 'زن' },
                    ]}
                    value={filters.gender}
                    onChange={(v) => {
                      setFilters((f) => ({ ...f, gender: v ?? null }))
                      setPage(1)
                    }}
                  />
                </Col>
                <Col xs={12} md={6}>
                  <Button
                    icon={<ClearOutlined />}
                    onClick={() => {
                      setFilters(EMPTY_FILTERS)
                      setPage(1)
                    }}
                  >
                    پاک‌سازی فیلترها
                  </Button>
                </Col>
                <Col xs={24} md={12}>
                  <Select
                    mode="multiple"
                    placeholder="برچسب‌ها"
                    style={{ width: '100%' }}
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    options={(tags.data ?? []).map((t) => ({ value: t.id, label: t.name }))}
                    value={filters.tag_ids}
                    onChange={(v) => {
                      setFilters((f) => ({ ...f, tag_ids: v }))
                      setPage(1)
                    }}
                  />
                </Col>
                <Col xs={24} md={12}>
                  <Select
                    mode="multiple"
                    placeholder="تشخیص‌ها"
                    style={{ width: '100%' }}
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    options={(diagnoses.data ?? []).map((d) => ({
                      value: d.id,
                      label: d.name,
                    }))}
                    value={filters.diagnosis_ids}
                    onChange={(v) => {
                      setFilters((f) => ({ ...f, diagnosis_ids: v }))
                      setPage(1)
                    }}
                  />
                </Col>
              </Row>
          )}
          <Table<Page<Patient>['items'][number]>
            rowKey="id"
            loading={isLoading}
            dataSource={data?.items ?? []}
            pagination={{
              current: page,
              pageSize: 20,
              total: data?.total ?? 0,
              onChange: setPage,
              showTotal: (t) => `${toFaDigits(t)} بیمار`,
            }}
            columns={[
              {
                title: 'نام',
                render: (_, p) => (
                  <Link to={`/patients/${p.id}`}>{`${p.first_name} ${p.last_name}`}</Link>
                ),
              },
              { title: 'کد ملی', dataIndex: 'national_id', render: (v) => toFaDigits(v) },
              {
                title: 'برچسب‌ها',
                render: (_, p) => (
                  <Space wrap>
                    {p.tags.map((t) => (
                      <Tag key={t.id} color="blue">
                        {t.name}
                      </Tag>
                    ))}
                    {p.diagnoses.map((d) => (
                      <Tag key={d.id} color="red">
                        {d.name}
                      </Tag>
                    ))}
                  </Space>
                ),
              },
              {
                title: 'عملیات',
                render: (_, p) => (
                  <Space>
                    <Button
                      size="small"
                      onClick={() => {
                        setEditing(p)
                        setModalOpen(true)
                      }}
                    >
                      ویرایش
                    </Button>
                    {hasPerm('patients.delete') && (
                      <Popconfirm
                        title="بیمار به سبد بازیافت منتقل شود؟ (نوبت‌ها و فایل‌ها پنهان می‌شوند)"
                        onConfirm={() => remove.mutate(p.id)}
                      >
                        <Button size="small" danger>
                          حذف
                        </Button>
                      </Popconfirm>
                    )}
                  </Space>
                ),
              },
            ]}
          />
        </Space>
      </Card>

      <PatientFormModal
        open={modalOpen}
        patient={editing}
        onCancel={() => {
          setModalOpen(false)
          setEditing(null)
        }}
        onDone={() => {
          setModalOpen(false)
          setEditing(null)
        }}
      />
    </div>
  )
}
