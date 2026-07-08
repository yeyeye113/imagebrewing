// ============================================================
// Error Boundary — 全局错误处理
// ============================================================

import { Component, type ReactNode } from 'react'
import { Button } from '@/components/ui'
import { RefreshCw, AlertTriangle } from 'lucide-react'

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
  onReset?: () => void
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
  errorInfo: string
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = {
      hasError: false,
      error: null,
      errorInfo: '',
    }
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    this.setState({
      error,
      errorInfo: errorInfo.componentStack || '',
    })
    console.error('[ErrorBoundary]', error, errorInfo)
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: '',
    })
    this.props.onReset?.()
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }
      return (
        <div className="min-h-[400px] flex items-center justify-center">
          <div className="text-center max-w-md mx-auto px-6">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-red-50 mb-4">
              <AlertTriangle className="w-8 h-8 text-red-500" />
            </div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">
              出错了
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              抱歉，应用遇到了一些问题。你可以尝试刷新页面重试。
            </p>
            {process.env.NODE_ENV === 'development' && this.state.error && (
              <details className="text-left mb-4 p-3 bg-gray-50 rounded-lg text-xs">
                <summary className="font-medium text-gray-700 cursor-pointer">
                  错误详情 (开发模式)
                </summary>
                <pre className="mt-2 text-red-600 overflow-auto">
                  {this.state.error.message}
                  {'\n\n'}
                  {this.state.errorInfo}
                </pre>
              </details>
            )}
            <div className="flex gap-3 justify-center">
              <Button variant="secondary" onClick={() => window.location.reload()}>
                <RefreshCw className="w-4 h-4 mr-2" />
                刷新页面
              </Button>
              <Button onClick={this.handleReset}>
                重试
              </Button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

// 简单的异步操作错误处理 Hook
export function withErrorHandler<T extends object>(
  WrappedComponent: React.ComponentType<T>,
  errorCallback?: (error: Error) => void
): React.ComponentType<T> {
  return function WithErrorHandler(props: T) {
    return (
      <ErrorBoundary onReset={errorCallback}>
        <WrappedComponent {...props} />
      </ErrorBoundary>
    )
  }
}
