import { useState, useEffect, useRef } from 'react'
import { CONFIG } from '../config'
import type { V5PlatformState, V5CoordinatorHealth } from '../types/vda5050'

export interface PlatformStateResult {
  /** Full platform state from coordinator /state */
  state: V5PlatformState | null
  /** Coordinator /health response */
  health: V5CoordinatorHealth | null
  /** Whether the coordinator is reachable */
  connected: boolean
  /** Last error message */
  error: string | null
  /** Manual refresh trigger */
  refresh: () => void
}

const POLL_INTERVAL_MS = 5000

export function usePlatformState(): PlatformStateResult {
  const [state, setState] = useState<V5PlatformState | null>(null)
  const [health, setHealth] = useState<V5CoordinatorHealth | null>(null)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const mountedRef = useRef(true)
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchData = async () => {
    try {
      // Fetch health first (unauthenticated)
      const healthRes = await fetch(`${CONFIG.apiBase}/v1/v5/health`, { cache: 'no-store' })
      if (!healthRes.ok) {
        if (mountedRef.current) {
          setConnected(false)
          setError(`Coordinator health: HTTP ${healthRes.status}`)
        }
        return
      }
      const healthData = await healthRes.json() as V5CoordinatorHealth
      if (mountedRef.current) {
        setHealth(healthData)
        setConnected(true)
        setError(null)
      }

      // Fetch platform state
      const stateRes = await fetch(`${CONFIG.apiBase}/v1/v5/state`, { cache: 'no-store' })
      if (stateRes.ok) {
        const stateData = await stateRes.json() as V5PlatformState
        if (mountedRef.current) setState(stateData)
      }
    } catch (err) {
      if (mountedRef.current) {
        setConnected(false)
        setError((err as Error).message)
      }
    }
  }

  useEffect(() => {
    mountedRef.current = true
    fetchData()
    pollTimer.current = setInterval(fetchData, POLL_INTERVAL_MS)
    return () => {
      mountedRef.current = false
      if (pollTimer.current) clearInterval(pollTimer.current)
    }
  }, [])

  return { state, health, connected, error, refresh: fetchData }
}
