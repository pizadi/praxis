import { useState } from 'react'
import { Button, Card, Form, Input, Typography, App as AntApp, theme as antdTheme } from 'antd'
import { useNavigate } from 'react-router-dom'

import { api, apiError, setTokens, type StoredUser } from '../api/client'

export default function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [loading, setLoading] = useState(false)
  const { message } = AntApp.useApp()
  const navigate = useNavigate()
  const { token } = antdTheme.useToken()

  const finish = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      const res = await api.post('/auth/login', values)
      setTokens(res.data.access_token, res.data.refresh_token, {
        id: 0,
        username: values.username,
        full_name: '',
        role_id: 0,
        role_name: '',
        permissions: [],
      })
      const me = await api.get('/auth/me')
      const user: StoredUser = {
        id: me.data.id,
        username: me.data.username,
        full_name: me.data.full_name,
        role_id: me.data.role_id,
        role_name: me.data.role_name,
        permissions: me.data.permissions ?? [],
      }
      setTokens(res.data.access_token, res.data.refresh_token, user)
      window.dispatchEvent(new Event('clinic-auth-changed'))
      onLogin()
      navigate('/')
    } catch (err) {
      const e = apiError(err)
      message.error(
        e.code === 'login_locked'
          ? 'تلاش‌های ناموفق بیش از حد مجاز؛ کمی بعد دوباره تلاش کنید'
          : e.message,
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        display: 'grid',
        placeItems: 'center',
        height: '100vh',
        background: token.colorBgLayout,
      }}
    >
      <Card style={{ width: 360, textAlign: 'center' }}>
        <Typography.Title level={3}>پراکسیس</Typography.Title>
        <Form layout="vertical" onFinish={finish}>
          <Form.Item
            name="username"
            label="نام کاربری"
            rules={[{ required: true, message: 'نام کاربری الزامی است' }]}
          >
            <Input autoFocus />
          </Form.Item>
          <Form.Item
            name="password"
            label="گذرواژه"
            rules={[{ required: true, message: 'گذرواژه الزامی است' }]}
          >
            <Input.Password />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            ورود
          </Button>
        </Form>
      </Card>
    </div>
  )
}
