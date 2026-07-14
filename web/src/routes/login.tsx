import { createFileRoute, redirect, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { TabGlyph } from '@/components/Logo'
import { isAuthenticated, login, register } from '@/lib/auth'

export const Route = createFileRoute('/login')({
  beforeLoad: () => {
    if (isAuthenticated()) throw redirect({ to: '/' })
  },
  component: LoginPage,
})

function LoginPage() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<'signin' | 'register'>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (mode === 'signin') await login(email, password)
      else await register(email, password)
      navigate({ to: '/' })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-paper px-4">
      <div className="w-full max-w-sm">
        <div className="mb-10 flex flex-col items-center text-center">
          <TabGlyph size={40} />
          <h1 className="font-display mt-4 text-[26px] font-bold tracking-tight">ProDocs</h1>
          <p className="mt-1 text-ink-muted">Paperwork, filed.</p>
        </div>

        <form onSubmit={submit} className="card p-6">
          <h2 className="font-display mb-4 text-[17px] font-semibold">
            {mode === 'signin' ? 'Sign in' : 'Create your account'}
          </h2>

          <label className="mb-3 block">
            <span className="eyebrow mb-1 block">Email</span>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-[14px] placeholder:text-ink-faint"
              placeholder="you@example.com"
            />
          </label>

          <label className="mb-4 block">
            <span className="eyebrow mb-1 block">Password</span>
            <input
              type="password"
              required
              minLength={6}
              autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-[14px]"
              placeholder="••••••••"
            />
          </label>

          {error && (
            <p role="alert" className="mb-3 rounded-lg bg-failed-soft px-3 py-2 text-[13px] text-failed">
              {error}
            </p>
          )}

          <button type="submit" disabled={busy} className="btn-primary w-full justify-center">
            {busy ? 'One moment…' : mode === 'signin' ? 'Sign in' : 'Create account'}
          </button>

          <button
            type="button"
            onClick={() => setMode(mode === 'signin' ? 'register' : 'signin')}
            className="mt-4 w-full text-center text-[13px] text-ink-muted hover:text-ink"
          >
            {mode === 'signin' ? 'New here? Create an account' : 'Already registered? Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
