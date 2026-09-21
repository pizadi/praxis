// Shared API types (mirror backend schemas)

export interface NamedRef {
  id: number
  name: string
}

export interface User {
  id: number
  username: string
  full_name: string
  role_id: number
  role_name: string
  permissions: string[]
  is_active: boolean
  created_at: string
}

export interface Role {
  id: number
  name: string
  is_system: boolean
  permissions: string[]
  user_count: number
  created_at: string
}

export interface PermissionItem {
  key: string
  label: string
}

export interface PermissionGroup {
  group: string
  items: PermissionItem[]
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
  /** files belong to the PATIENT since 1.3 (they survive appointment deletion) */
  patient_id: number
  description: string
  notes: string
  /** server-side storage name (UUID) — changes when the content is replaced */
  stored_filename: string | null
  original_filename: string | null
  mime_type: string | null
  size_bytes: number | null
  missing_file: boolean
  created_at: string
  updated_at: string
}

export interface PrescriptionItemLink {
  id: number
  item_id: number
  item_name: string
  quantity: number | null
}

export interface Prescription {
  id: number
  patient_id: number
  prescribed_at: string
  notes: string
  created_by_username: string | null
  /** legacy provenance: appointment the prescription was migrated from */
  source_appointment_id: number | null
  items: PrescriptionItemLink[]
  created_at: string
  updated_at: string
}

export interface PrescriptionItemInput {
  item_id?: number
  name?: string
  quantity?: number | null
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

export interface QuestionnaireTemplate {
  id: number
  name: string
  description: string
  format: import('../lib/questionnaire').FormatDoc
  created_at: string
  updated_at: string
}

export interface QuestionnaireResponse {
  id: number
  patient_id: number
  template_id: number
  template_name: string
  answers: import('../lib/questionnaire').Answers
  created_by_username: string | null
  created_at: string
  updated_at: string
}

export interface QuestionnaireResponseReport extends QuestionnaireResponse {
  patient_national_id: string
}
