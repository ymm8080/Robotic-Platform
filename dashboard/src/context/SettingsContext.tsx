import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import {
  type UserSettings,
  DEFAULT_SETTINGS,
  type SettingsField,
  SETTINGS_FIELDS,
} from '../types/settings'
import { loadSession } from '../types/auth'

interface SettingsContextValue {
  settings: UserSettings
  updateSetting: <K extends keyof UserSettings>(key: K, value: UserSettings[K]) => void
  resetDefaults: () => void
  saveMessage: string | null
  fields: SettingsField[]
}

const SettingsContext = createContext<SettingsContextValue | null>(null)

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext)
  if (!ctx) throw new Error('useSettings must be used within SettingsProvider')
  return ctx
}

const SETTINGS_PREFIX = 'robot_dashboard_settings_'

function getStorageKey(): string {
  const userId = loadSession()
  return `${SETTINGS_PREFIX}${userId || 'default'}`
}

function readSettings(): UserSettings {
  try {
    const raw = localStorage.getItem(getStorageKey())
    if (!raw) return { ...DEFAULT_SETTINGS }
    const parsed = JSON.parse(raw)
    return { ...DEFAULT_SETTINGS, ...parsed }
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

function writeSettings(settings: UserSettings): void {
  localStorage.setItem(getStorageKey(), JSON.stringify(settings))
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<UserSettings>(readSettings)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const [msgTimer, setMsgTimer] = useState<ReturnType<typeof setTimeout> | null>(null)

  // Re-read settings if session changes (user login/logout)
  useEffect(() => {
    setSettings(readSettings())
  }, [])

  const updateSetting = useCallback(<K extends keyof UserSettings>(key: K, value: UserSettings[K]) => {
    setSettings(prev => {
      const next = { ...prev, [key]: value }
      writeSettings(next)
      return next
    })
    // Show "Saved" message briefly
    if (msgTimer) clearTimeout(msgTimer)
    setSaveMessage('Saved')
    const t = setTimeout(() => setSaveMessage(null), 2000)
    setMsgTimer(t)
  }, [msgTimer])

  const resetDefaults = useCallback(() => {
    setSettings({ ...DEFAULT_SETTINGS })
    writeSettings({ ...DEFAULT_SETTINGS })
    if (msgTimer) clearTimeout(msgTimer)
    setSaveMessage('Reset to defaults')
    const t = setTimeout(() => setSaveMessage(null), 2000)
    setMsgTimer(t)
  }, [msgTimer])

  return (
    <SettingsContext.Provider value={{
      settings,
      updateSetting,
      resetDefaults,
      saveMessage,
      fields: SETTINGS_FIELDS,
    }}>
      {children}
    </SettingsContext.Provider>
  )
}
