/** Auth types and helpers — localStorage-backed with API-ready design */

export type UserRole = 'admin' | 'user'

export interface FunctionArea {
  key: string
  label: string
}

export interface FunctionRole {
  key: string
  label: string
  description: string
}

/** Available function areas a user can be assigned to */
export const FUNCTION_AREAS: FunctionArea[] = [
  { key: 'warehouse_a', label: 'Warehouse A' },
  { key: 'warehouse_b', label: 'Warehouse B' },
  { key: 'fleet_ops', label: 'Fleet Operations' },
  { key: 'maintenance', label: 'Maintenance' },
  { key: 'order_mgmt', label: 'Order Management' },
  { key: 'monitoring', label: 'Monitoring' },
  { key: 'system_admin', label: 'System Administration' },
]

/** Available function roles within each area */
export const FUNCTION_ROLES: FunctionRole[] = [
  { key: 'operator', label: 'Operator', description: 'Day-to-day robot task execution' },
  { key: 'supervisor', label: 'Supervisor', description: 'Oversee operations and resolve exceptions' },
  { key: 'manager', label: 'Manager', description: 'Manage fleet, schedules, and reports' },
  { key: 'auditor', label: 'Auditor', description: 'Review logs, compliance, and performance' },
  { key: 'maintainer', label: 'Maintainer', description: 'Robot maintenance and diagnostics' },
  { key: 'dispatcher', label: 'Dispatcher', description: 'Create and assign transport orders' },
]

export interface User {
  id: string
  username: string
  email: string
  phone: string
  role: UserRole
  functionAreas: string[]   // keys from FUNCTION_AREAS
  functionRoles: string[]   // keys from FUNCTION_ROLES
  createdAt: string
  passwordHash: string
}

export interface LoginPayload {
  username: string
  password: string
  role: UserRole
}

export interface RegisterPayload {
  username: string
  email: string
  phone: string
  password: string
  role: UserRole
}

export interface AuthState {
  currentUser: Omit<User, 'passwordHash'> | null
  isAuthenticated: boolean
  isAdmin: boolean
  error: string | null
}

/** Seed a default admin user */
export function getDefaultAdmin(): User {
  return {
    id: 'admin-seed-000',
    username: 'Admin',
    email: 'admin@robot.local',
    phone: '',
    role: 'admin',
    functionAreas: ['system_admin'],
    functionRoles: ['manager', 'auditor'],
    createdAt: new Date().toISOString(),
    passwordHash: '', // will be set on first write
  }
}

/** Hash a password using PBKDF2 (SHA-512, 100k iterations) via Web Crypto API.
 *  Returns "salt:hash" format — salt is stored alongside the hash. */
export async function hashPassword(password: string): Promise<string> {
  const encoder = new TextEncoder()
  const salt = crypto.getRandomValues(new Uint8Array(16))
  const keyMaterial = await crypto.subtle.importKey(
    'raw', encoder.encode(password), 'PBKDF2', false, ['deriveBits'],
  )
  const derived = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', salt, iterations: 100_000, hash: 'SHA-512' },
    keyMaterial, 256,
  )
  const hashHex = Array.from(new Uint8Array(derived)).map(b => b.toString(16).padStart(2, '0')).join('')
  const saltHex = Array.from(salt).map(b => b.toString(16).padStart(2, '0')).join('')
  return `${saltHex}:${hashHex}`
}

/** Verify a password against a PBKDF2 hash (in "salt:hash" format).
 *  Falls back to SHA-256 comparison for legacy hashes (no colon = old format). */
export async function verifyPassword(password: string, stored: string): Promise<boolean> {
  if (!stored.includes(':')) {
    // Legacy SHA-256 hash — re-hash and compare
    const encoder = new TextEncoder()
    const data = encoder.encode(password)
    const hashBuffer = await crypto.subtle.digest('SHA-256', data)
    const hashArray = Array.from(new Uint8Array(hashBuffer))
    const legacyHash = hashArray.map(b => b.toString(16).padStart(2, '0')).join('')
    return legacyHash === stored
  }
  const [saltHex, hashHex] = stored.split(':')
  const salt = new Uint8Array(saltHex.match(/.{2}/g)!.map(b => parseInt(b, 16)))
  const encoder = new TextEncoder()
  const keyMaterial = await crypto.subtle.importKey(
    'raw', encoder.encode(password), 'PBKDF2', false, ['deriveBits'],
  )
  const derived = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', salt, iterations: 100_000, hash: 'SHA-512' },
    keyMaterial, 256,
  )
  const derivedHex = Array.from(new Uint8Array(derived)).map(b => b.toString(16).padStart(2, '0')).join('')
  return derivedHex === hashHex
}

/** Generate a simple unique ID */
export function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

/** Strip sensitive fields from a User for safe exposure */
export function safeUser(user: User): Omit<User, 'passwordHash'> {
  const { passwordHash: _, ...safe } = user
  return safe
}

/** Validate phone number (basic: digits, +, spaces, dashes, min 7 digits) */
export function isValidPhone(phone: string): boolean {
  if (!phone.trim()) return false
  const digits = phone.replace(/[\s\-\+\(\)]/g, '')
  return /^\d{7,15}$/.test(digits)
}

/** Validate email */
export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())
}

/** Login can use either email or phone + password */
export function matchCredential(user: User, credential: string): boolean {
  const c = credential.trim().toLowerCase()
  if (user.email?.toLowerCase() === c) return true
  if (user.phone) {
    return user.phone.replace(/[\s\-\+\(\)]/g, '') === c.replace(/[\s\-\+\(\)]/g, '')
  }
  return false
}

const USERS_KEY = 'robot_dashboard_users'
const SESSION_KEY = 'robot_dashboard_session'

const DEFAULT_ADMIN_PASSWORD = 'admin123'

export async function getOrSeedUsers(): Promise<User[]> {
  const existing = loadUsers()
  if (existing.length > 0) return existing
  // Seed default admin
  const admin = getDefaultAdmin()
  admin.passwordHash = await hashPassword(DEFAULT_ADMIN_PASSWORD)
  const seeded = [admin]
  saveUsers(seeded)
  return seeded
}

export function loadUsers(): User[] {
  try {
    const raw = localStorage.getItem(USERS_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

export function saveUsers(users: User[]): void {
  localStorage.setItem(USERS_KEY, JSON.stringify(users))
}

export function loadSession(): string | null {
  return localStorage.getItem(SESSION_KEY)
}

export function saveSession(userId: string): void {
  localStorage.setItem(SESSION_KEY, userId)
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY)
}
