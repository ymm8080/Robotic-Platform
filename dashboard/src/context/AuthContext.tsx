import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import {
  type User,
  type UserRole,
  type AuthState,
  hashPassword,
  generateId,
  safeUser,
  isValidPhone,
  isValidEmail,
  matchCredential,
  getOrSeedUsers,
  loadUsers,
  saveUsers,
  loadSession,
  saveSession,
  clearSession,
  FUNCTION_ROLES,
} from '../types/auth'
import { areaLabel as loadAreaLabel } from '../hooks/useAreas'

export type { UserRole }

interface UserSummary {
  id: string
  username: string
  email: string
  phone: string
  role: UserRole
  functionAreas: string[]
  functionRoles: string[]
  createdAt: string
}

interface AuthContextValue extends AuthState {
  login: (credential: string, password: string, role: UserRole) => Promise<void>
  register: (username: string, email: string, phone: string, password: string, role: UserRole) => Promise<void>
  logout: () => void
  users: UserSummary[]
  updateUser: (userId: string, updates: Partial<Pick<User, 'functionAreas' | 'functionRoles' | 'role'>>) => void
  deleteUser: (userId: string) => void
  areaLabel: (key: string) => string
  roleLabel: (key: string) => string
}

const AuthContext = createContext<AuthContextValue | null>(null)

/** Raw context — use for non-throwing access (e.g. tests, optional guards). Prefer useAuth() for normal usage. */
export { AuthContext as AuthContextRaw }

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

const STORAGE_KEY = 'robot_dashboard_users'
const SESSION_KEY = 'robot_dashboard_session'

/** Normalize and migrate old user records that lack newer fields */
function normalizeUser(u: Partial<User> & { id: string }): User {
  return {
    id: u.id,
    username: u.username ?? '',
    email: u.email ?? '',
    phone: u.phone ?? '',
    role: u.role ?? 'user',
    functionAreas: Array.isArray(u.functionAreas) ? u.functionAreas : [],
    functionRoles: Array.isArray(u.functionRoles) ? u.functionRoles : [],
    createdAt: u.createdAt ?? new Date().toISOString(),
    passwordHash: u.passwordHash ?? '',
  }
}

function readUsers(): User[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map(normalizeUser)
  } catch {
    return []
  }
}

function writeUsers(users: User[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(users))
}

function roleLabel(key: string): string {
  return FUNCTION_ROLES.find(r => r.key === key)?.label ?? key
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    currentUser: null,
    isAuthenticated: false,
    isAdmin: false,
    error: null,
  })
  const [userList, setUserList] = useState<User[]>([])

  // Seed admin + restore session on mount
  useEffect(() => {
    let active = true
    ;(async () => {
      const seeded = await getOrSeedUsers()
      if (!active) return
      setUserList(seeded)

      const sessionId = loadSession()
      if (sessionId) {
        const found = seeded.find(u => u.id === sessionId)
        if (found) {
          setState({
            currentUser: safeUser(found),
            isAuthenticated: true,
            isAdmin: found.role === 'admin',
            error: null,
          })
        } else {
          clearSession()
        }
      }
    })()
    return () => { active = false }
  }, [])

  const login = useCallback(async (credential: string, password: string, role: UserRole) => {
    const all = readUsers()
    const h = await hashPassword(password)

    // Find user by email or phone matching the credential
    const found = all.find(u => matchCredential(u, credential) && u.passwordHash === h)

    if (!found) {
      setState(prev => ({ ...prev, error: 'Invalid credentials' }))
      throw new Error('Invalid email/phone or password')
    }

    if (found.role !== role) {
      setState(prev => ({ ...prev, error: 'Invalid role selection for this account' }))
      throw new Error(`This account is registered as "${found.role}", not "${role}". Please select the correct role.`)
    }

    saveSession(found.id)
    setState({
      currentUser: safeUser(found),
      isAuthenticated: true,
      isAdmin: found.role === 'admin',
      error: null,
    })
  }, [])

  const register = useCallback(async (
    username: string, email: string, phone: string, password: string, role: UserRole,
  ) => {
    const all = readUsers()

    // Validation
    if (!username.trim()) throw new Error('Username is required')
    if (username.trim().length < 3) throw new Error('Username must be at least 3 characters')
    if (!email.trim() && !phone.trim()) throw new Error('Email or phone number is required')
    if (email.trim() && !isValidEmail(email)) throw new Error('Invalid email format')
    if (phone.trim() && !isValidPhone(phone)) throw new Error('Phone must be 7-15 digits')
    if (!password || password.length < 6) throw new Error('Password must be at least 6 characters')

    if (all.find(u => u.username === username.trim())) {
      throw new Error('Username already exists')
    }
    if (email.trim() && all.find(u => u.email.toLowerCase() === email.trim().toLowerCase())) {
      throw new Error('Email already registered')
    }
    if (phone.trim() && all.find(u => u.phone && u.phone.replace(/[\s\-\+\(\)]/g, '') === phone.replace(/[\s\-\+\(\)]/g, ''))) {
      throw new Error('Phone number already registered')
    }

    const newUser: User = {
      id: generateId(),
      username: username.trim(),
      email: email.trim().toLowerCase(),
      phone: phone.trim(),
      role,
      functionAreas: [],
      functionRoles: [],
      createdAt: new Date().toISOString(),
      passwordHash: await hashPassword(password),
    }

    const updated = [...all, newUser]
    writeUsers(updated)
    setUserList(updated)
    saveSession(newUser.id)
    setState({
      currentUser: safeUser(newUser),
      isAuthenticated: true,
      isAdmin: role === 'admin',
      error: null,
    })
  }, [])

  const logout = useCallback(() => {
    clearSession()
    setState({ currentUser: null, isAuthenticated: false, isAdmin: false, error: null })
  }, [])

  const updateUser = useCallback((userId: string, updates: Partial<Pick<User, 'functionAreas' | 'functionRoles' | 'role'>>) => {
    const all = readUsers()
    const idx = all.findIndex(u => u.id === userId)
    if (idx === -1) return
    all[idx] = { ...all[idx], ...updates }
    writeUsers(all)
    setUserList(all)

    // If updating the current user, refresh session state
    const sessionId = loadSession()
    if (userId === sessionId) {
      const updated = all[idx]
      setState(prev => ({
        ...prev,
        currentUser: safeUser(updated),
        isAdmin: updated.role === 'admin',
      }))
    }
  }, [])

  const deleteUser = useCallback((userId: string) => {
    const all = readUsers()
    const filtered = all.filter(u => u.id !== userId)
    writeUsers(filtered)
    setUserList(filtered)
  }, [])

  const userSummaries: UserSummary[] = userList.map(u => ({
    id: u.id,
    username: u.username,
    email: u.email,
    phone: u.phone,
    role: u.role,
    functionAreas: u.functionAreas,
    functionRoles: u.functionRoles,
    createdAt: u.createdAt,
  }))

  return (
    <AuthContext.Provider value={{
      ...state, login, register, logout, users: userSummaries,
      updateUser, deleteUser, areaLabel: loadAreaLabel, roleLabel,
    }}>
      {children}
    </AuthContext.Provider>
  )
}
