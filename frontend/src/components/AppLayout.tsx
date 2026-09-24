import { createContext, useContext, useCallback, useRef, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Button, Drawer, Dropdown, Layout, Menu, Typography, theme as antdTheme } from 'antd'
import {
  CheckOutlined,
  LogoutOutlined,
  MenuOutlined,
} from '@ant-design/icons'

import { clearAuth, api, getRefreshToken, hasPerm, type StoredUser } from '../api/client'
import BackupStaleAlert from './BackupStaleAlert'
import { roleFa } from '../lib/roles'
import { useIsMobile } from '../lib/useIsMobile'
import { THEMES, type Palette } from '../lib/themes'
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
      { key: '/taxonomies', label: 'موجودیت‌ها' },
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

/** Compact palette swatch: the theme's background/primary pair in one chip. */
function PaletteSwatch({ palette }: { palette: Palette }) {
  const { token } = antdTheme.useToken()
  return (
    <span
      aria-hidden
      style={{
        display: 'inline-block',
        width: 14,
        height: 14,
        borderRadius: 7,
        border: `1px solid ${token.colorBorderSecondary}`,
        background: `linear-gradient(135deg, ${palette.map.colorBgLayout} 50%, ${palette.seed.colorPrimary} 50%)`,
        verticalAlign: 'middle',
      }}
    />
  )
}

/** Session-scoped VibeFarsi theme switcher — replaces the old night-mode
 * toggle; «کاغذ» is the light option, the rest are curated dark palettes. */
function ThemeSwitcher() {
  const { theme, setTheme } = useTheme()
  const items = THEMES.map((p) => ({
    key: p.id,
    label: (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
        <PaletteSwatch palette={p} />
        {p.label}
        {p.scheme === 'light' && (
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
            روشن
          </Typography.Text>
        )}
      </span>
    ),
    icon: p.id === theme.id ? <CheckOutlined /> : <span style={{ width: 14 }} />,
  }))
  return (
    <Dropdown
      trigger={['click']}
      placement="bottomLeft"
      menu={{
        items,
        selectable: true,
        selectedKeys: [theme.id],
        onClick: ({ key }) => setTheme(key as Palette['id']),
      }}
    >
      <Button title="تم" icon={<PaletteSwatch palette={theme} />} />
    </Dropdown>
  )
}

interface Props {
  user: StoredUser
  onLogout: () => void
}

export default function AppLayout({ user, onLogout }: Props) {
  const navigate = useNavigate()
  const location = useLocation()
  const { token } = antdTheme.useToken()
  const isMobile = useIsMobile()
  const [navOpen, setNavOpen] = useState(false)
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

  const menuGroups = GROUPS.map((g) => ({
    type: 'group' as const,
    label: g.title,
    children: g.items
      .filter((i) => !i.perm || can(i.perm))
      .map(({ key, label }) => ({ key, label })),
  })).filter((g) => g.children.length > 0)

  const doLogout = () => {
    // revoke the refresh token server-side (best effort — the local session
    // is cleared regardless; without this the token would stay valid 7 days)
    const refresh = getRefreshToken()
    if (refresh) api.post('/auth/logout', { refresh_token: refresh }).catch(() => {})
    clearAuth()
    window.dispatchEvent(new Event('clinic-auth-changed'))
    onLogout()
  }

  const menuStyle = { borderInlineEnd: 'none', paddingTop: 12, background: 'transparent' }

  const nav = isMobile ? (
    <Drawer
      title="پراکسیس"
      placement="right"
      width={260}
      open={navOpen}
      onClose={() => setNavOpen(false)}
      styles={{ body: { padding: 0 } }}
    >
      <Menu
        mode="inline"
        selectedKeys={[selected]}
        items={menuGroups}
        onClick={({ key }) => {
          setNavOpen(false)
          navigateGuarded(key)
        }}
        style={menuStyle}
      />
      <div style={{ padding: '12px 16px' }}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {user.full_name || user.username} ({roleFa(user.role_name)})
        </Typography.Text>
      </div>
    </Drawer>
  ) : (
    <Sider
      width={200}
      theme="light"
      style={{
        background: token.colorBgContainer,
        borderInlineEnd: `1px solid ${token.colorBorderSecondary}`,
      }}
    >
      <Menu
        mode="inline"
        selectedKeys={[selected]}
        items={menuGroups}
        onClick={({ key }) => navigateGuarded(key)}
        style={menuStyle}
      />
    </Sider>
  )

  return (
    <NavGuardCtx.Provider value={{ registerNavBlocker, navigateGuarded }}>
      <UserCtx.Provider value={{ user, hasPerm: can }}>
        <Layout style={{ minHeight: '100vh' }}>
        <Header
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
            background: token.colorBgContainer,
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            paddingInline: isMobile ? 12 : 24,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
            {isMobile && (
              <Button
                type="text"
                icon={<MenuOutlined />}
                onClick={() => setNavOpen(true)}
                title="منو"
                aria-label="منو"
              />
            )}
            <Typography.Title level={4} style={{ margin: 0, whiteSpace: 'nowrap' }}>
              پراکسیس
              {!isMobile && (
                <Typography.Text
                  type="secondary"
                  style={{ fontSize: 12, marginInlineStart: 10, direction: 'ltr', unicodeBidi: 'embed' }}
                >
                  v{__APP_VERSION__}
                </Typography.Text>
              )}
            </Typography.Title>
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            {!isMobile && (
              <Typography.Text>
                {user.full_name || user.username} ({roleFa(user.role_name)})
              </Typography.Text>
            )}
            <ThemeSwitcher />
            <Button icon={<LogoutOutlined />} onClick={doLogout}>
              خروج
            </Button>
          </div>
        </Header>
        <Layout>
          {nav}
          <Content style={{ padding: isMobile ? 12 : 24, overflow: 'auto', height: 'calc(100vh - 64px)' }}>
            <BackupStaleAlert />
            <Outlet />
          </Content>
        </Layout>
      </Layout>
      </UserCtx.Provider>
    </NavGuardCtx.Provider>
  )
}
