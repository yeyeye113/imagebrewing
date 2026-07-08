// ============================================================
// LoginPage — 登录预留
// ============================================================

import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Card, CardHeader, CardContent, Button, Input } from '@/components/ui'
import { DevNotice } from '@/components/DevNotice'
import { ThemeToggle } from '@/components/ThemeToggle'
import { LanguageToggle } from '@/components/LanguageToggle'
import { useAccountStore } from '@/store/account'
import { apiLogin } from '@/lib/api/auth'
import { useT } from '@/hooks/useT'
import { LogIn } from 'lucide-react'

export default function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const returnTo = searchParams.get('return') || '/'
  const { session, hydrated, hydrate } = useAccountStore()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const tr = useT()

  useEffect(() => {
    hydrate()
  }, [hydrate])

  useEffect(() => {
    if (hydrated && session) {
      navigate(returnTo, { replace: true })
    }
  }, [hydrated, session, navigate, returnTo])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!email.trim()) {
      setError(tr('login.emailRequired'))
      return
    }
    if (password.length < 6) {
      setError(tr('login.passwordShort'))
      return
    }
    try {
      await apiLogin({ email, password })
      navigate(returnTo, { replace: true })
    } catch {
      setError(tr('login.failed'))
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 flex flex-col">
      <header className="flex items-center justify-between px-4 py-4 max-w-lg mx-auto w-full">
        <Link to="/" className="text-sm font-semibold text-gray-900 dark:text-gray-100 hover:opacity-80">
          Future Simulation Engine
        </Link>
        <div className="flex items-center gap-2">
          <LanguageToggle />
          <ThemeToggle compact />
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-4 pb-12 pt-[env(safe-area-inset-top)]">
        <div className="w-full max-w-md space-y-4">
          <DevNotice title={tr('login.devTitle')} detail={tr('login.devDetail')} />

          <Card>
            <CardHeader>
              <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                <LogIn className="w-5 h-5" />
                {tr('login.title')}
              </h1>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{tr('login.subtitle')}</p>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <Input
                  label={tr('login.email')}
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => { setEmail(e.target.value); setError('') }}
                  error={error && !email.trim() ? error : undefined}
                />
                <Input
                  label={tr('login.password')}
                  type="password"
                  autoComplete="current-password"
                  placeholder={tr('login.passwordPh')}
                  value={password}
                  onChange={(e) => { setPassword(e.target.value); setError('') }}
                />
                {error && email.trim() && <p className="text-xs text-red-500">{error}</p>}
                <Button type="submit" className="w-full">{tr('login.submit')}</Button>
              </form>

              <div className="mt-6 pt-4 border-t border-gray-100 dark:border-gray-800 text-center space-y-2">
                <p className="text-xs text-gray-400 dark:text-gray-500">{tr('login.registerHint')}</p>
                <Link to="/" className="text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200">
                  {tr('login.skip')}
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  )
}
