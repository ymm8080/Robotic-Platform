import { useState, type FormEvent } from 'react'
import { useAuth } from '../context/AuthContext'
import type { UserRole } from '../types/auth'

type Mode = 'login' | 'register'

export function AuthPage() {
  const { login, register, error } = useAuth()
  const [mode, setMode] = useState<Mode>('login')

  // Login fields
  const [credential, setCredential] = useState('')
  const [password, setPassword] = useState('')
  const [loginRole, setLoginRole] = useState<UserRole>('user')

  // Register fields
  const [regUsername, setRegUsername] = useState('')
  const [regEmail, setRegEmail] = useState('')
  const [regPhone, setRegPhone] = useState('')
  const [regPassword, setRegPassword] = useState('')
  const [regConfirm, setRegConfirm] = useState('')
  const [regRole, setRegRole] = useState<UserRole>('user')

  const [submitting, setSubmitting] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)

  const displayError = localError || error

  async function handleLogin(e: FormEvent) {
    e.preventDefault()
    setLocalError(null)
    if (!credential.trim() || !password) {
      setLocalError('Please enter email/phone and password')
      return
    }
    setSubmitting(true)
    try {
      await login(credential.trim(), password, loginRole)
    } catch (err) {
      setLocalError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRegister(e: FormEvent) {
    e.preventDefault()
    setLocalError(null)

    if (!regUsername.trim() || !regPassword) {
      setLocalError('Username and password are required')
      return
    }
    if (!regEmail.trim() && !regPhone.trim()) {
      setLocalError('Email or phone number is required')
      return
    }
    if (regPassword !== regConfirm) {
      setLocalError('Passwords do not match')
      return
    }

    setSubmitting(true)
    try {
      await register(regUsername.trim(), regEmail.trim(), regPhone.trim(), regPassword, regRole)
    } catch (err) {
      setLocalError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  function switchMode(m: Mode) {
    setMode(m)
    setLocalError(null)
  }

  return (
    <div style={{
      maxWidth: 440, margin: '60px auto 0', padding: '24px',
      fontFamily: 'system-ui, -apple-system, sans-serif',
    }}>
      {/* Header */}
      <div style={{ textAlign: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, margin: '0 0 4px', color: '#111827' }}>
          🤖 Robot Dispatch Platform
        </h1>
        <p style={{ fontSize: 13, color: '#6b7280', margin: 0 }}>
          SAP-EWM · VDA5050
        </p>
      </div>

      {/* Card */}
      <div style={{
        background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12,
        padding: '24px', boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
      }}>
        {/* Mode tabs */}
        <div style={{ display: 'flex', marginBottom: 20, borderRadius: 8, background: '#f3f4f6', padding: 3 }}>
          <button onClick={() => switchMode('login')}
            style={{
              flex: 1, padding: '8px 0', fontSize: 14, fontWeight: mode === 'login' ? 600 : 400,
              border: 'none', borderRadius: 6, cursor: 'pointer',
              background: mode === 'login' ? '#fff' : 'transparent',
              color: mode === 'login' ? '#111827' : '#6b7280',
              boxShadow: mode === 'login' ? '0 1px 2px rgba(0,0,0,0.08)' : 'none',
              transition: 'all 0.15s',
            }}>
            Sign In
          </button>
          <button onClick={() => switchMode('register')}
            style={{
              flex: 1, padding: '8px 0', fontSize: 14, fontWeight: mode === 'register' ? 600 : 400,
              border: 'none', borderRadius: 6, cursor: 'pointer',
              background: mode === 'register' ? '#fff' : 'transparent',
              color: mode === 'register' ? '#111827' : '#6b7280',
              boxShadow: mode === 'register' ? '0 1px 2px rgba(0,0,0,0.08)' : 'none',
              transition: 'all 0.15s',
            }}>
            Register
          </button>
        </div>

        {/* Seed admin hint */}
        <div style={{
          background: '#eff6ff', border: '1px solid #bfdbfe', color: '#1d4ed8',
          padding: '8px 12px', borderRadius: 6, fontSize: 12, marginBottom: 16,
        }}>
          💡 Default admin: <strong>admin@robot.local</strong> / <strong>admin123</strong> (select Admin role)
        </div>

        {/* Error banner */}
        {displayError && (
          <div style={{
            background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c',
            padding: '8px 12px', borderRadius: 6, fontSize: 13, marginBottom: 16,
          }}>
            {displayError}
          </div>
        )}

        {mode === 'login' ? (
          <form onSubmit={handleLogin}>
            <Field label="Email or Phone" type="text" value={credential}
              onChange={e => setCredential(e.target.value)}
              placeholder="your@email.com or +8613800138000" autoFocus
            />
            <Field label="Password" type="password" value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="Enter password"
            />
            {/* Role dropdown */}
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
                Role
              </label>
              <select
                value={loginRole}
                onChange={e => setLoginRole(e.target.value as UserRole)}
                style={{
                  width: '100%', padding: '8px 12px', fontSize: 14,
                  border: '1px solid #d1d5db', borderRadius: 6,
                  outline: 'none', boxSizing: 'border-box',
                  fontFamily: 'inherit', background: '#fff',
                  cursor: 'pointer',
                }}
                onFocus={e => { e.currentTarget.style.borderColor = '#3b82f6' }}
                onBlur={e => { e.currentTarget.style.borderColor = '#d1d5db' }}
              >
                <option value="user">👤 Normal User</option>
                <option value="admin">🛡️ Admin</option>
              </select>
            </div>

            <button type="submit" disabled={submitting}
              style={{
                width: '100%', marginTop: 8, padding: '10px 0', fontSize: 15, fontWeight: 600,
                background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 8,
                cursor: submitting ? 'not-allowed' : 'pointer',
                opacity: submitting ? 0.6 : 1,
              }}>
              {submitting ? 'Signing in…' : 'Sign In'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleRegister}>
            <Field label="Username" type="text" value={regUsername}
              onChange={e => setRegUsername(e.target.value)}
              placeholder="Choose a username (min 3 chars)" autoFocus
            />
            <Field label="Email" type="email" value={regEmail}
              onChange={e => setRegEmail(e.target.value)}
              placeholder="your@email.com"
            />
            <Field label="Phone (optional if email provided)" type="tel" value={regPhone}
              onChange={e => setRegPhone(e.target.value)}
              placeholder="+8613800138000"
            />
            {/* Role dropdown */}
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
                Role
              </label>
              <select
                value={regRole}
                onChange={e => setRegRole(e.target.value as UserRole)}
                style={{
                  width: '100%', padding: '8px 12px', fontSize: 14,
                  border: '1px solid #d1d5db', borderRadius: 6,
                  outline: 'none', boxSizing: 'border-box',
                  fontFamily: 'inherit', background: '#fff',
                  cursor: 'pointer',
                }}
                onFocus={e => { e.currentTarget.style.borderColor = '#3b82f6' }}
                onBlur={e => { e.currentTarget.style.borderColor = '#d1d5db' }}
              >
                <option value="user">👤 Normal User</option>
                <option value="admin">🛡️ Admin</option>
              </select>
            </div>

            <Field label="Password" type="password" value={regPassword}
              onChange={e => setRegPassword(e.target.value)}
              placeholder="Min 6 characters"
            />
            <Field label="Confirm Password" type="password" value={regConfirm}
              onChange={e => setRegConfirm(e.target.value)}
              placeholder="Re-enter password"
            />
            <button type="submit" disabled={submitting}
              style={{
                width: '100%', marginTop: 8, padding: '10px 0', fontSize: 15, fontWeight: 600,
                background: '#22c55e', color: '#fff', border: 'none', borderRadius: 8,
                cursor: submitting ? 'not-allowed' : 'pointer',
                opacity: submitting ? 0.6 : 1,
              }}>
              {submitting ? 'Creating account…' : 'Create Account'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}

function Field({ label, ...inputProps }: {
  label: string
  type: string
  value: string
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void
  placeholder: string
  autoFocus?: boolean
}) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 4 }}>
        {label}
      </label>
      <input {...inputProps}
        style={{
          width: '100%', padding: '8px 12px', fontSize: 14,
          border: '1px solid #d1d5db', borderRadius: 6,
          outline: 'none', boxSizing: 'border-box',
          transition: 'border-color 0.15s',
          fontFamily: 'inherit',
        }}
        onFocus={e => { e.currentTarget.style.borderColor = '#3b82f6' }}
        onBlur={e => { e.currentTarget.style.borderColor = '#d1d5db' }}
      />
    </div>
  )
}
