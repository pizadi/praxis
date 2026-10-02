import { Button, Card, Table, Typography } from 'antd'
import { PlusOutlined } from '@ant-design/icons'

import type { Attachment } from '../../api/types'
import { fileSize, formatJalali } from '../../lib/jalali'
import FaNumber from '../FaNumber'
import StackCell from '../StackCell'

interface Props {
  files: Attachment[]
  loading: boolean
  selectedId: number | null
  canWrite: boolean
  onSelect: (fileId: number) => void
  onNew: () => void
}

/** Patient-level file list; the detail pane is rendered by the parent page.
 * One stacked column everywhere (no desktop/mobile split): row 1 is the
 * title + upload date, row 2 the filename + size (or «بدون فایل» for a
 * note-only row). */
export default function FileSidebarCard({
  files,
  loading,
  selectedId,
  canWrite,
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
        rowClassName={(file) => (selectedId === file.id ? 'ant-table-row-selected' : '')}
        onRow={(file) => ({
          onClick: () => onSelect(file.id),
          style: { cursor: 'pointer' },
        })}
        columns={[
          {
            title: 'فایل',
            render: (_, file) => {
              const title = file.description || file.original_filename || 'یادداشت'
              return (
                <StackCell
                  main={
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'baseline',
                        justifyContent: 'space-between',
                        gap: 8,
                        minWidth: 0,
                      }}
                    >
                      <Typography.Text ellipsis>{title}</Typography.Text>
                      <Typography.Text type="secondary" style={{ fontSize: 12, flexShrink: 0 }}>
                        <FaNumber value={formatJalali(file.created_at)} />
                      </Typography.Text>
                    </div>
                  }
                  lines={[
                    file.original_filename ? (
                      <span key="name">
                        {file.original_filename}
                        {' — '}
                        <FaNumber value={fileSize(file.size_bytes)} />
                      </span>
                    ) : (
                      'بدون فایل'
                    ),
                  ]}
                />
              )
            },
          },
        ]}
      />
    </Card>
  )
}
