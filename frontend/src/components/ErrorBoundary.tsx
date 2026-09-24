import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button, Card, Typography } from 'antd'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/**
 * Render-error containment: a crashing page shows a Persian error card
 * (with a reload action) instead of silently blanking the whole app —
 * React unmounts the entire tree on an uncaught render error.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // the stack is the only clue when a machine-specific rendering bug is
    // reported (e.g. an older browser) — keep it in the console
    console.error('render error:', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <Card>
          <Typography.Title level={4}>خطا در نمایش این صفحه</Typography.Title>
          <Typography.Paragraph type="secondary" style={{ direction: 'ltr', unicodeBidi: 'embed' }}>
            {String(this.state.error)}
          </Typography.Paragraph>
          <Button type="primary" onClick={() => window.location.reload()}>
            بارگذاری مجدد صفحه
          </Button>
        </Card>
      )
    }
    return this.props.children
  }
}
