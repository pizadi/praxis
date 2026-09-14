import { createContext, useContext } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Layout, Menu, Button, Typography, theme as antdTheme } from 'antd'
import { LogoutOutlined, MoonOutlined, SunOutlined } from '@ant-design/icons'

import { clearAuth, type StoredUser } from '../api/client'
import { useTheme } from './ThemeContext'

const { Header, Content, Sider } = Layout

const ITEMS = [
  { key: '/', label: 'داشبورد' },
  { key: '/schedule', label: 'برنامه روزانه' },
  { key: '/payments', label: 'پرداخت‌های امروز' },
  { key: '/patients', label: 'بیماران' },
  { key: '/taxonomies', label: 'برچسب‌ها و تشخیص‌ها' },
  { key: '/stats', label: 'آمار' },
]

export const UserCtx = createContext<{ user: StoredUser; isDoctor: boolean }>({
  user: { id: 0, username: '', full_name: '', role: 'receptionist' },
  isDoctor: false,
})

export function useUser() {
  return useContext(UserCtx)
}

interface Props {
  user: StoredUser
  onLogout: () => void
}

export default function AppLayout({ user, onLogout }: Props) {
  const navigate = useNavigate()
  const location = useLocation()
  const { isDark, toggle } = useTheme()
  const { token } = antdTheme.useToken()
  const isDoctor = user.role === 'doctor' || user.role === 'admin'
  const isAdmin = user.role === 'admin'

  const selected =
    ITEMS.map((i) => i.key)
      .filter((k) => location.pathname.startsWith(k) && k !== '/')
      .sort((a, b) => b.length - a.length)[0] ?? '/'

  const doLogout = () => {
    clearAuth()
    window.dispatchEvent(new Event('clinic-auth-changed'))
    onLogout()
  }

  return (
    <UserCtx.Provider value={{ user, isDoctor }}>
      <Layout style={{ minHeight: '100vh' }}>
        <Header
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: token.colorBgContainer,
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
          }}
        >
          <Typography.Title level={4} style={{ margin: 0 }}>
            سامانه مطب
          </Typography.Title>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <Typography.Text>
              {user.full_name || user.username} (
              {user.role === 'admin' ? 'مدیر' : user.role === 'doctor' ? 'پزشک' : 'پذیرش'})
            </Typography.Text>
            <Button
              icon={isDark ? <SunOutlined /> : <MoonOutlined />}
              onClick={toggle}
              title={isDark ? 'حالت روشن' : 'حالت تیره'}
            />
            <Button icon={<LogoutOutlined />} onClick={doLogout}>
              خروج
            </Button>
          </div>
        </Header>
        <Layout>
          <Sider theme={isDark ? 'dark' : 'light'} width={200}>
            <Menu
              mode="inline"
              selectedKeys={[selected]}
              items={[
                ...ITEMS,
                ...(isDoctor ? [{ key: '/trash', label: 'سبد بازیافت' }] : []),
                ...(isAdmin ? [{ key: '/users', label: 'کاربران' }] : []),
                ...(isAdmin ? [{ key: '/audit', label: 'گزارش اقدامات' }] : []),
              ]}
              onClick={({ key }) => navigate(key)}
              style={{ borderInlineEnd: 'none', paddingTop: 12 }}
            />
          </Sider>
          <Content style={{ padding: 24, overflowY: 'auto', height: 'calc(100vh - 64px)' }}>
            <Outlet />
          </Content>
        </Layout>
      </Layout>
    </UserCtx.Provider>
  )
}
