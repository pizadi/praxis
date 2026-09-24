import { Button, Card, Table, Typography } from 'antd'
import { PlusOutlined } from '@ant-design/icons'

import type { Attachment } from '../../api/types'
import { fileSize } from '../../lib/jalali'
import StackCell from '../StackCell'

interface Props {
  files: Attachment[]
  loading: boolean
  selectedId: number | null
  canWrite: boolean
  isMobile: boolean
  onSelect: (fileId: number) => void
  onNew: () => void
}

/** Patient-level file list; the detail pane is rendered by the parent page. */
export default function FileSidebarCard({
  files,
  loading,
  selectedId,
  canWrite,
  isMobile,
  onSelect,
  onNew,
}: Props) {
  return (
    <Card
      title="همه فایل‌ها"
      extra={
        canWrite && (
          <Button type="primary" size="small" icon={<PlusOutlined />} onClick={onNew}>
            افزودن فایل
          </Button>
        )
      }
      styles={{ body: { padding: 0 } }}
    >
      <Table<Attachment>
        rowKey="id"
        size="small"
        loading={loading}
        dataSource={files}
        locale={{ emptyText: 'فایلی موجود نیست' }}
        scroll={isMobile ? undefined : { x: 'max-content' }}
        rowClassName={(file) => (selectedId === file.id ? 'ant-table-row-selected' : '')}
        onRow={(file) => ({
          onClick: () => onSelect(file.id),
          style: { cursor: 'pointer' },
        })}
        columns={
          isMobile
            ? [
                {
                  title: 'فایل',
                  render: (_, file) => (
                    <StackCell
                      main={file.description || file.original_filename || 'یادداشت'}
                      lines={[
                        file.description && file.original_filename
                          ? file.original_filename
                          : null,
                        fileSize(file.size_bytes),
                      ]}
                    />
                  ),
                },
              ]
            : [
                { title: 'شرح', dataIndex: 'description' },
                {
                  title: 'نام فایل',
                  dataIndex: 'original_filename',
                  render: (name: string | null) =>
                    name ?? <Typography.Text type="secondary">بدون فایل</Typography.Text>,
                },
                { title: 'حجم', dataIndex: 'size_bytes', render: fileSize },
              ]
        }
      />
    </Card>
  )
}
