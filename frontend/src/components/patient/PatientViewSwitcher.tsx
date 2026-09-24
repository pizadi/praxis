import { Segmented } from 'antd'
import {
  CalendarOutlined,
  FileDoneOutlined,
  FileOutlined,
  MedicineBoxOutlined,
} from '@ant-design/icons'

export type ViewMode = 'appointments' | 'files' | 'questionnaires' | 'prescriptions'

interface Props {
  value: ViewMode
  onChange: (value: ViewMode) => void
}

/** The four patient-page views; navigation is guarded by the parent page. */
export default function PatientViewSwitcher({ value, onChange }: Props) {
  return (
    <Segmented<ViewMode>
      block
      value={value}
      onChange={onChange}
      options={[
        { value: 'appointments', label: 'نوبت‌ها', icon: <CalendarOutlined /> },
        { value: 'files', label: 'همه فایل‌ها', icon: <FileOutlined /> },
        { value: 'questionnaires', label: 'پرسش‌نامه‌ها', icon: <FileDoneOutlined /> },
        { value: 'prescriptions', label: 'نسخه‌ها', icon: <MedicineBoxOutlined /> },
      ]}
    />
  )
}
