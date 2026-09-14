// Shared API types (mirror backend schemas)

export interface NamedRef {
  id: number
  name: string
}

export interface User {
  id: number
  username: string
  full_name: string
  role: 'admin' | 'doctor' | 'receptionist'
  is_active: boolean
  created_at: string
}

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface Patient {
  id: number
  national_id: string
  first_name: string
  last_name: string
  insurance: string | null
  year_of_birth: string
  phone_number: string
  gender: number
  tags: NamedRef[]
  diagnoses: NamedRef[]
  created_at: string
  updated_at: string
}

export interface Appointment {
  id: number
  patient_id: number
  scheduled_at: string
  notes: string
  cm: string
  hx: string
  px: string
  rx: string
  patient_first_name: string
  patient_last_name: string
  patient_national_id: string
  created_at: string
  updated_at: string
}

export interface AppointmentBrief {
  id: number
  patient_id: number
  scheduled_at: string
  patient_first_name: string
  patient_last_name: string
  patient_national_id: string
  attachment_count: number
}

export interface Transaction {
  id: number
  appointment_id: number
  description: string
  amount: number
  pos: boolean
}

export interface PatientTransaction extends Transaction {
  appointment_scheduled_at: string
}

export interface Attachment {
  id: number
  appointment_id: number
  description: string
  notes: string
  original_filename: string | null
  mime_type: string | null
  size_bytes: number | null
  missing_file: boolean
  created_at: string
  updated_at: string
}

export interface DescriptionStat {
  description: string
  count: number
  total_amount: number
}

export interface StatsSummary {
  start: string
  end: string
  num_appointments: number
  total_amount: number
  pos_amount: number
  cash_amount: number
  num_transactions: number
  by_description: DescriptionStat[]
}
