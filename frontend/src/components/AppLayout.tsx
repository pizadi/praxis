import { createContext, useContext, useCallback, useRef } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Layout, Menu, Button, Typography, theme as antdTheme } from 'antd'
import { LogoutOutlined, MoonOutlined, SunOutlined } from '@ant-design/icons'

import { clearAuth, api, getRefreshToken, hasPerm, type StoredUser } from '../api/client'
import { roleFa } from '../lib/roles'
import { NavGuardCtx, type NavBlocker } from './NavGuard'
import { useTheme } from './ThemeContext'

const { Header, Content, Sider } = Layout

type MenuItem = { key: string; label: string; perm?: string }

/** Sidebar sections; each group hides entirely when none of its items is
 * permitted for the current user. */
const GROUPS: { title: string; items: MenuItem[] }[] = [
  {
    title: 'عملیات روزانه',
    items: [
      { key: '/', label: 'داشبورد' },
      { key: '/schedule', label: 'برنامه روزانه' },
      { key: '/patients', label: 'بیماران' },
    ],
  },
  {
    title: 'مالی',
    items: [
      { key: '/payments', label: 'پرداخت‌های امروز', perm: 'payments.view' },
      { key: '/stats', label: 'آمار', perm: 'stats.view' },
    ],
  },
  {
    title: 'پرسش‌نامه‌ها',
    items: [
      { key: '/questionnaires', label: 'قالب پرسش‌نامه‌ها', perm: 'questionnaires.templates' },
      { key: '/questionnaire-responses', label: 'گزارش پاسخ‌ها', perm: 'questionnaires.read' },
    ],
  },
  {
    title: 'مدیریت',
    items: [
      { key: '/taxonomies', label: 'برچسب‌ها، تشخیص‌ها و نسخه‌ها' },
      { key: '/users', label: 'کاربران', perm: 'users.manage' },
      { key: '/roles', label: 'نقش‌ها و دسترسی‌ها', perm: 'roles.manage' },
      { key: '/trash', label: 'سبد بازیافت', perm: 'trash.view' },
      { key: '/backup', label: 'پشتیبان‌گیری', perm: 'backup.manage' },
      { key: '/audit', label: 'گزارش اقدامات', perm: 'audit.view' },
    ],
  },
]

export const UserCtx = createContext<{
  user: StoredUser
  hasPerm: (...perms: string[]) => boolean
}>({
  user: { id: 0, username: '', full_name: '', role_id: 0, role_name: '', permissions: [] },
  hasPerm: () => false,
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
  const can = (...perms: string[]) => hasPerm(user, ...perms)

  // route-level unsaved-changes guard (see NavGuard.tsx): the mounted page
  // registers a blocker; menu navigations are then confirmed by the page's
  // own save/discard/stay dialog instead of happening silently
  const blockerRef = useRef<NavBlocker | null>(null)
  const registerNavBlocker = useCallback((b: NavBlocker | null) => {
    blockerRef.current = b
  }, [])
  const navigateGuarded = useCallback(
    (to: string) => {
      const b = blockerRef.current
      if (b && b.isDirty()) b.requestLeave(to)
      else navigate(to)
    },
    [navigate],
  )

  const selected =
    GROUPS.flatMap((g) => g.items.map((i) => i.key))
      .filter((k) => k !== '/' && location.pathname.startsWith(k))
      .sort((a, b) => b.length - a.length)[0] ?? '/'

  const doLogout = () => {
    // revoke the refresh token server-side (best effort — the local session
    // is cleared regardless; without this the token would stay valid 7 days)
    const refresh = getRefreshToken()
    if (refresh) api.post('/auth/logout', { refresh_token: refresh }).catch(() => {})
    clearAuth()
    window.dispatchEvent(new Event('clinic-auth-changed'))
    onLogout()
  }

  return (
    <NavGuardCtx.Provider value={{ registerNavBlocker, navigateGuarded }}>
      <UserCtx.Provider value={{ user, hasPerm: can }}>
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
            پراکسیس
            <Typography.Text
              type="secondary"
              style={{ fontSize: 12, marginInlineStart: 10, direction: 'ltr', unicodeBidi: 'embed' }}
            >
              v{__APP_VERSION__}
            </Typography.Text>
          </Typography.Title>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <Typography.Text>
              {user.full_name || user.username} ({roleFa(user.role_name)})
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
              items={GROUPS.map((g) => ({
                type: 'group' as const,
                label: g.title,
                children: g.items
                  .filter((i) => !i.perm || can(i.perm))
                  .map(({ key, label }) => ({ key, label })),
              })).filter((g) => g.children.length > 0)}
              onClick={({ key }) => navigateGuarded(key)}
              style={{ borderInlineEnd: 'none', paddingTop: 12 }}
            />
          </Sider>
          <Content style={{ padding: 24, overflowY: 'auto', height: 'calc(100vh - 64px)' }}>
            <Outlet />
          </Content>
        </Layout>
      </Layout>
      </UserCtx.Provider>
    </NavGuardCtx.Provider>
  )
}
