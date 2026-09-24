import { Button, Card, Descriptions, Popconfirm, Space, Tag } from 'antd'
import { DeleteOutlined, EditOutlined } from '@ant-design/icons'

import type { NamedRef, Patient } from '../../api/types'
import { toFaDigits } from '../../lib/jalali'

interface Props {
  patient: Patient
  canDelete: boolean
  onEdit: () => void
  onDelete: () => void
}

/** Patient identity card at the top of the patient-page sidebar. */
export default function PatientInfoCard({ patient, canDelete, onEdit, onDelete }: Props) {
  return (
    <Card
      title={`${patient.first_name} ${patient.last_name}`}
      extra={
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={onEdit}>
            ویرایش
          </Button>
          {canDelete && (
            <Popconfirm
              title="بیمار به سبد بازیافت منتقل شود؟ (نوبت‌ها و فایل‌ها پنهان می‌شوند)"
              onConfirm={onDelete}
            >
              <Button size="small" danger icon={<DeleteOutlined />}>
                حذف
              </Button>
            </Popconfirm>
          )}
        </Space>
      }
    >
      <Descriptions bordered column={1} size="small">
        <Descriptions.Item label="کد ملی">
          {toFaDigits(patient.national_id)}
        </Descriptions.Item>
        <Descriptions.Item label="تلفن">
          {toFaDigits(patient.phone_number) || '—'}
        </Descriptions.Item>
        <Descriptions.Item label="بیمه">{patient.insurance || '—'}</Descriptions.Item>
        <Descriptions.Item label="سال تولد">
          {toFaDigits(patient.year_of_birth)}
        </Descriptions.Item>
        <Descriptions.Item label="جنسیت">
          {patient.gender === 0 ? 'مرد' : 'زن'}
        </Descriptions.Item>
        <Descriptions.Item label="برچسب‌ها">
          <Space wrap>
            {patient.tags.length === 0 && patient.diagnoses.length === 0 && '—'}
            {patient.tags.map((tag: NamedRef) => (
              <Tag key={tag.id} color="blue">
                {tag.name}
              </Tag>
            ))}
            {patient.diagnoses.map((diagnosis: NamedRef) => (
              <Tag key={diagnosis.id} color="red">
                {diagnosis.name}
              </Tag>
            ))}
          </Space>
        </Descriptions.Item>
      </Descriptions>
    </Card>
  )
}
