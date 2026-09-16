import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  App as AntApp,
  Button,
  Col,
  Form,
  Input,
  Row,
  Space,
  Typography,
} from 'antd'

import { api, apiError } from '../api/client'
import type { Attachment } from '../api/types'
import { useUser } from './AppLayout'

/**
 * Expanded-row content for file tables: shows the file's notes and
 * (for doctors) an inline edit form for description + notes.
 */
export default function FileNotesExpanded({ file }: { file: Attachment }) {
  const { hasPerm } = useUser()
  const { message } = AntApp.useApp()
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)

  const save = useMutation({
    mutationFn: async (values: { description: string; notes: string }) =>
      api.patch(`/appointments/files/${file.id}`, values),
    onSuccess: async () => {
      message.success('ذخیره شد')
      setEditing(false)
      await qc.invalidateQueries({ queryKey: ['appointment-files'] })
      await qc.invalidateQueries({ queryKey: ['patient-files'] })
    },
    onError: (err) => message.error(apiError(err).message),
  })

  if (editing) {
    return (
      <Form
        layout="vertical"
        initialValues={{ description: file.description, notes: file.notes }}
        onFinish={(v: { description: string; notes: string }) => save.mutate(v)}
      >
        <Row gutter={12}>
          <Col span={12}>
            <Form.Item name="description" label="شرح">
              <Input maxLength={128} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="notes" label="یادداشت">
              <Input.TextArea rows={3} maxLength={10000} />
            </Form.Item>
          </Col>
        </Row>
        <Space>
          <Button type="primary" htmlType="submit" loading={save.isPending}>
            ذخیره
          </Button>
          <Button onClick={() => setEditing(false)}>انصراف</Button>
        </Space>
      </Form>
    )
  }

  return (
    <Space direction="vertical" size="small" style={{ width: '100%' }}>
      <Typography.Paragraph
        style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}
      >
        {file.notes.trim() ? file.notes : 'بدون یادداشت'}
      </Typography.Paragraph>
      {hasPerm('files.write') && (
        <Button size="small" onClick={() => setEditing(true)}>
          ویرایش شرح و یادداشت
        </Button>
      )}
    </Space>
  )
}
