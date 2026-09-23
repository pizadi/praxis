import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConfigProvider, App as AntApp } from 'antd'
import faIR from 'antd/locale/fa_IR'
import { HashRouter } from 'react-router-dom'

import App from './App'
import { useThemeState, ThemeContext } from './components/ThemeContext'
import { algorithmFor } from './lib/themes'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 15_000 },
  },
})

function Root() {
  const { ctx, palette } = useThemeState()
  return (
    <ThemeContext.Provider value={ctx}>
      <ConfigProvider
        direction="rtl"
        locale={faIR}
        theme={{
          token: {
            fontFamily: 'Vazirmatn, system-ui, sans-serif',
            ...palette.seed,
          },
          // palette seed tokens drive the base light/dark algorithm, then the
          // palette's exact surface/text/border tokens are applied on top
          algorithm: algorithmFor(palette),
        }}
      >
        <AntApp>
          <QueryClientProvider client={queryClient}>
            <HashRouter>
              <App />
            </HashRouter>
          </QueryClientProvider>
        </AntApp>
      </ConfigProvider>
    </ThemeContext.Provider>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
