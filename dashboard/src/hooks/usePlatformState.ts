import { useState, useEffect, useRef, useCallback } from 'react'
import { CONFIG } from '../config'
import type { V5PlatformState, V5CoordinatorHealth, WORMPlaybackEvent } from '../types/vda5050'

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
  /** Recent WORM playback events (last 300s) */
  playbackEvents: WORMPlaybackEvent[]
  /** Loading state for playback */
  playbackLoading: boolean
}

const POLL_INTERVAL_MS = 1000
const PLAYBACK_INTERVAL_MS = 10_000

export function usePlatformState(): PlatformStateResult {
  const [state, setState] = useState<V5PlatformState | null>(null)
  const [health, setHealth] = useState<V5CoordinatorHealth | null>(null)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [playbackEvents, setPlaybackEvents] = useState<WORMPlaybackEvent[]>([])
  const [playbackLoading, setPlaybackLoading] = useState(false)
  const mountedRef = useRef(true)
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchData = useCallback(async () => {
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
  }, [])

  const fetchPlayback = useCallback(async () => {
    if (!mountedRef.current) return
    setPlaybackLoading(true)
    try {
      const res = await fetch(`${CONFIG.apiBase}/v1/v5/playback?duration=300`, { cache: 'no-store' })
      if (res.ok) {
        const data = await res.json()
        const events: WORMPlaybackEvent[] = data.events ?? []
        if (mountedRef.current) setPlaybackEvents(events)
      }
    } catch {
      // Silently ignore playback errors — non-critical
    } finally {
      if (mountedRef.current) setPlaybackLoading(false)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    fetchData()
    fetchPlayback()
    pollTimer.current = setInterval(fetchData, POLL_INTERVAL_MS)
    const pbTimer = setInterval(fetchPlayback, PLAYBACK_INTERVAL_MS)
    return () => {
      mountedRef.current = false
      if (pollTimer.current) clearInterval(pollTimer.current)
      clearInterval(pbTimer)
    }
  }, [fetchData, fetchPlayback])

  return { state, health, connected, error, refresh: fetchData, playbackEvents, playbackLoading }
}
